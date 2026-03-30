from __future__ import annotations

import base64
import re
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

import fitz
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, field_validator

ROOT_DIR = Path(__file__).resolve().parents[1]
TEMPLATE_PDF_CANDIDATES = [
    ROOT_DIR / "assets" / "templates" / "lav-bill-template.pdf",
    ROOT_DIR / "api" / "assets" / "templates" / "lav-bill-template.pdf",
]
PAGE_MARGIN_FILL = (1, 1, 1)
BLACK = (0, 0, 0)
MONEY_STEP = Decimal("0.01")


class BillRequest(BaseModel):
    invoice_date: date
    customer_name: str = Field(min_length=1, max_length=120)
    customer_address: str = Field(min_length=1, max_length=280)
    bags: int = Field(ge=1, le=100000)
    rate_including_tax: Decimal = Field(ge=Decimal("0.01"), decimal_places=2)
    product_description: str = Field(default="Cement @ 18%", min_length=1, max_length=80)
    hsn_sac: str = Field(default="25232930", min_length=4, max_length=20)
    invoice_number: str = Field(default="SCT/2025-26/1224", min_length=4, max_length=40)
    eway_bill_number: str = Field(default="721610668584", min_length=6, max_length=24)
    cgst_rate: Decimal = Field(default=Decimal("9.00"), ge=Decimal("0.00"), le=Decimal("100.00"))
    sgst_rate: Decimal = Field(default=Decimal("9.00"), ge=Decimal("0.00"), le=Decimal("100.00"))

    @field_validator("customer_name", "customer_address", "product_description", "invoice_number", "eway_bill_number")
    @classmethod
    def strip_text(cls, value: str) -> str:
        collapsed = re.sub(r"\s+", " ", value).strip()
        if not collapsed:
            raise ValueError("This field cannot be empty.")
        return collapsed

    @field_validator("hsn_sac")
    @classmethod
    def normalize_hsn(cls, value: str) -> str:
        cleaned = re.sub(r"\s+", "", value)
        if not cleaned:
            raise ValueError("HSN/SAC cannot be empty.")
        return cleaned


class BillCalculation(BaseModel):
    formatted_date: str
    quantity_label: str
    unit_label: str
    base_rate: str
    rate_including_tax: str
    taxable_amount: str
    cgst_amount: str
    sgst_amount: str
    rounding_adjustment: str
    tax_amount: str
    total_amount: str
    total_amount_words: str
    tax_amount_words: str


class BillRenderResponse(BaseModel):
    file_name: str
    pdf_base64: str
    calculation: BillCalculation


DEFAULT_BILL = BillRequest(
    invoice_date=date(2026, 2, 21),
    customer_name="LAV MANAV SAH",
    customer_address="G-2 18/21 Ratiya Marg, Sangam Vihar, New Delhi, South Delhi, Delhi, 110080",
    bags=500,
    rate_including_tax=Decimal("350.00"),
)


def resolve_template_pdf() -> Path:
    for candidate in TEMPLATE_PDF_CANDIDATES:
        if candidate.exists():
            return candidate
    return TEMPLATE_PDF_CANDIDATES[0]


def money(value: Decimal) -> Decimal:
    return value.quantize(MONEY_STEP, rounding=ROUND_HALF_UP)


def format_indian_money(value: Decimal) -> str:
    amount = money(value)
    sign = "-" if amount < 0 else ""
    amount = abs(amount)
    raw = f"{amount:.2f}"
    integer_part, fraction = raw.split(".")

    if len(integer_part) <= 3:
        grouped = integer_part
    else:
        last_three = integer_part[-3:]
        leading = integer_part[:-3]
        chunks: list[str] = []
        while leading:
            chunks.append(leading[-2:])
            leading = leading[:-2]
        grouped = ",".join(reversed(chunks)) + f",{last_three}"

    return f"{sign}{grouped}.{fraction}"


def number_to_words_under_thousand(number: int) -> str:
    ones = [
        "",
        "One",
        "Two",
        "Three",
        "Four",
        "Five",
        "Six",
        "Seven",
        "Eight",
        "Nine",
        "Ten",
        "Eleven",
        "Twelve",
        "Thirteen",
        "Fourteen",
        "Fifteen",
        "Sixteen",
        "Seventeen",
        "Eighteen",
        "Nineteen",
    ]
    tens = [
        "",
        "",
        "Twenty",
        "Thirty",
        "Forty",
        "Fifty",
        "Sixty",
        "Seventy",
        "Eighty",
        "Ninety",
    ]

    words: list[str] = []
    hundreds, remainder = divmod(number, 100)
    if hundreds:
        words.extend([ones[hundreds], "Hundred"])
    if remainder:
        if remainder < 20:
            words.append(ones[remainder])
        else:
            ten_value, unit = divmod(remainder, 10)
            words.append(tens[ten_value])
            if unit:
                words.append(ones[unit])
    return " ".join(part for part in words if part)


def number_to_words_indian(number: int) -> str:
    if number == 0:
        return "Zero"

    parts: list[str] = []
    crore, number = divmod(number, 10_000_000)
    lakh, number = divmod(number, 100_000)
    thousand, number = divmod(number, 1_000)
    hundred_chunk = number

    if crore:
        parts.append(f"{number_to_words_under_thousand(crore)} Crore")
    if lakh:
        parts.append(f"{number_to_words_under_thousand(lakh)} Lakh")
    if thousand:
        parts.append(f"{number_to_words_under_thousand(thousand)} Thousand")
    if hundred_chunk:
        parts.append(number_to_words_under_thousand(hundred_chunk))

    return " ".join(parts)


def amount_to_words(value: Decimal) -> str:
    normalized = money(value)
    rupees = int(normalized)
    paise = int((normalized - Decimal(rupees)) * 100)
    rupee_words = number_to_words_indian(rupees)
    if paise:
        return f"INR {rupee_words} and {number_to_words_indian(paise)} Paise Only"
    return f"INR {rupee_words} Only"


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "updated-bill"


def fit_font_size(text: str, width: float, max_size: float, min_size: float, fontname: str) -> float:
    size = max_size
    while size > min_size and fitz.get_text_length(text, fontname=fontname, fontsize=size) > width:
        size -= 0.2
    return round(max(size, min_size), 2)


def wrap_text(text: str, width: float, fontname: str, fontsize: float, max_lines: int) -> list[str]:
    words = text.split()
    lines: list[str] = []
    current = ""

    for word in words:
        candidate = f"{current} {word}".strip()
        if not current or fitz.get_text_length(candidate, fontname=fontname, fontsize=fontsize) <= width:
            current = candidate
            continue
        lines.append(current)
        current = word

    if current:
        lines.append(current)

    if len(lines) <= max_lines:
        return lines

    trimmed = lines[: max_lines - 1]
    last_line_words = " ".join(lines[max_lines - 1 :]).split()
    last = ""
    for word in last_line_words:
        candidate = f"{last} {word}".strip()
        if fitz.get_text_length(candidate, fontname=fontname, fontsize=fontsize) <= width:
            last = candidate
        else:
            while last and fitz.get_text_length(last + "...", fontname=fontname, fontsize=fontsize) > width:
                last = last[:-1].rstrip()
            trimmed.append((last + "...").strip())
            return trimmed

    trimmed.append(last)
    return trimmed[:max_lines]


def paint_rect(page: fitz.Page, rect: fitz.Rect) -> None:
    page.draw_rect(rect, color=None, fill=PAGE_MARGIN_FILL, overlay=True)


def draw_single_line(
    page: fitz.Page,
    rect: fitz.Rect,
    text: str,
    *,
    align: int = fitz.TEXT_ALIGN_LEFT,
    fontname: str = "helv",
    max_size: float = 10.4,
    min_size: float = 7.4,
) -> None:
    paint_rect(page, rect)
    fontsize = fit_font_size(text, rect.width - 2, max_size, min_size, fontname)
    text_width = fitz.get_text_length(text, fontname=fontname, fontsize=fontsize)

    if align == fitz.TEXT_ALIGN_RIGHT:
        x = rect.x1 - text_width - 1
    elif align == fitz.TEXT_ALIGN_CENTER:
        x = rect.x0 + max((rect.width - text_width) / 2, 1)
    else:
        x = rect.x0 + 1

    y = rect.y0 + fontsize + max((rect.height - fontsize) / 2 - 1, 0)
    page.insert_text(
        fitz.Point(x, y),
        text,
        fontname=fontname,
        fontsize=fontsize,
        color=BLACK,
        overlay=True,
    )


def draw_multiline(
    page: fitz.Page,
    rect: fitz.Rect,
    text: str,
    *,
    fontname: str = "helv",
    max_size: float = 9.6,
    min_size: float = 7.2,
    max_lines: int = 2,
) -> None:
    paint_rect(page, rect)
    fontsize = max_size
    lines: list[str] = []

    while fontsize >= min_size:
        lines = wrap_text(text, rect.width - 2, fontname, fontsize, max_lines)
        required_height = len(lines) * (fontsize + 1.6)
        if len(lines) <= max_lines and required_height <= rect.height + 1:
            break
        fontsize -= 0.2

    y = rect.y0 + fontsize
    for line in lines[:max_lines]:
        page.insert_text(
            fitz.Point(rect.x0 + 1, y),
            line,
            fontname=fontname,
            fontsize=fontsize,
            color=BLACK,
            overlay=True,
        )
        y += fontsize + 1.6


def draw_customer_block(page: fitz.Page, rect: fitz.Rect, name: str, address: str) -> None:
    paint_rect(page, rect)

    name_rect = fitz.Rect(rect.x0, rect.y0, rect.x1, rect.y0 + 11.5)
    address_rect = fitz.Rect(rect.x0, rect.y0 + 12, rect.x1, rect.y1)

    draw_single_line(page, name_rect, name, fontname="helv", max_size=10.2, min_size=7.8)
    draw_multiline(page, address_rect, address, fontname="helv", max_size=9.2, min_size=7.0, max_lines=2)


def compute_bill(request: BillRequest) -> BillCalculation:
    total_rate = request.cgst_rate + request.sgst_rate
    divisor = Decimal("1.00") + (total_rate / Decimal("100.00"))
    base_rate = money(request.rate_including_tax / divisor)

    taxable_amount = money(base_rate * request.bags)
    cgst_amount = money(taxable_amount * request.cgst_rate / Decimal("100.00"))
    sgst_amount = money(taxable_amount * request.sgst_rate / Decimal("100.00"))
    total_amount = money(request.rate_including_tax * request.bags)
    tax_amount = money(cgst_amount + sgst_amount)
    rounding_adjustment = money(total_amount - taxable_amount - tax_amount)

    return BillCalculation(
        formatted_date=request.invoice_date.strftime("%d-%b-%y"),
        quantity_label=f"{request.bags} bgs",
        unit_label="BAG",
        base_rate=format_indian_money(base_rate),
        rate_including_tax=format_indian_money(request.rate_including_tax),
        taxable_amount=format_indian_money(taxable_amount),
        cgst_amount=format_indian_money(cgst_amount),
        sgst_amount=format_indian_money(sgst_amount),
        rounding_adjustment=format_indian_money(rounding_adjustment),
        tax_amount=format_indian_money(tax_amount),
        total_amount=format_indian_money(total_amount),
        total_amount_words=amount_to_words(total_amount),
        tax_amount_words=amount_to_words(tax_amount),
    )


def build_file_name(request: BillRequest) -> str:
    return f"{slugify(request.customer_name)}-{request.invoice_date.isoformat()}.pdf"


def render_pdf(request: BillRequest) -> bytes:
    template_pdf = resolve_template_pdf()
    if not template_pdf.exists():
        raise FileNotFoundError(f"Template PDF not found. Checked: {', '.join(str(path) for path in TEMPLATE_PDF_CANDIDATES)}")

    calculation = compute_bill(request)
    template = fitz.open(template_pdf)
    output = fitz.open()
    output.insert_pdf(template, from_page=0, to_page=1)

    invoice_page = output[0]
    eway_page = output[1]

    draw_single_line(invoice_page, fitz.Rect(275, 170, 328, 182), request.invoice_number, align=fitz.TEXT_ALIGN_LEFT)
    draw_single_line(invoice_page, fitz.Rect(338, 170, 388, 182), request.eway_bill_number, align=fitz.TEXT_ALIGN_LEFT)
    draw_single_line(invoice_page, fitz.Rect(390, 170, 438, 182), calculation.formatted_date, align=fitz.TEXT_ALIGN_LEFT)
    draw_customer_block(invoice_page, fitz.Rect(39, 241, 234, 277), request.customer_name, request.customer_address)
    draw_customer_block(invoice_page, fitz.Rect(39, 311, 234, 347), request.customer_name, request.customer_address)
    draw_single_line(invoice_page, fitz.Rect(52, 414, 196, 426), request.product_description, fontname="helv", max_size=9.6)
    draw_single_line(invoice_page, fitz.Rect(198, 414, 238, 426), request.hsn_sac, align=fitz.TEXT_ALIGN_RIGHT)
    draw_single_line(invoice_page, fitz.Rect(248, 414, 287, 426), calculation.quantity_label, align=fitz.TEXT_ALIGN_CENTER)
    draw_single_line(invoice_page, fitz.Rect(304, 414, 334, 426), calculation.rate_including_tax, align=fitz.TEXT_ALIGN_RIGHT)
    draw_single_line(invoice_page, fitz.Rect(350, 414, 381, 426), calculation.base_rate, align=fitz.TEXT_ALIGN_RIGHT)
    draw_single_line(invoice_page, fitz.Rect(447, 414, 501, 426), calculation.taxable_amount, align=fitz.TEXT_ALIGN_RIGHT)
    draw_single_line(invoice_page, fitz.Rect(456, 448, 501, 461), calculation.cgst_amount, align=fitz.TEXT_ALIGN_RIGHT)
    draw_single_line(invoice_page, fitz.Rect(456, 460, 501, 473), calculation.sgst_amount, align=fitz.TEXT_ALIGN_RIGHT)
    draw_single_line(invoice_page, fitz.Rect(474, 472, 501, 485), calculation.rounding_adjustment, align=fitz.TEXT_ALIGN_RIGHT)
    draw_single_line(invoice_page, fitz.Rect(248, 570, 287, 582), calculation.quantity_label, align=fitz.TEXT_ALIGN_CENTER)
    draw_single_line(invoice_page, fitz.Rect(446, 570, 501, 584), calculation.total_amount, align=fitz.TEXT_ALIGN_RIGHT, max_size=11.2)
    draw_single_line(invoice_page, fitz.Rect(39, 597, 300, 610), calculation.total_amount_words, max_size=10.0, min_size=6.6)
    draw_single_line(invoice_page, fitz.Rect(234, 632, 281, 643), calculation.taxable_amount, align=fitz.TEXT_ALIGN_RIGHT, max_size=8.4)
    draw_single_line(invoice_page, fitz.Rect(325, 632, 365, 643), calculation.cgst_amount, align=fitz.TEXT_ALIGN_RIGHT, max_size=8.4)
    draw_single_line(invoice_page, fitz.Rect(408, 632, 448, 643), calculation.sgst_amount, align=fitz.TEXT_ALIGN_RIGHT, max_size=8.4)
    draw_single_line(invoice_page, fitz.Rect(461, 632, 501, 643), calculation.tax_amount, align=fitz.TEXT_ALIGN_RIGHT, max_size=8.4)
    draw_single_line(invoice_page, fitz.Rect(234, 643, 281, 654), calculation.taxable_amount, align=fitz.TEXT_ALIGN_RIGHT, max_size=8.4)
    draw_single_line(invoice_page, fitz.Rect(325, 643, 365, 654), calculation.cgst_amount, align=fitz.TEXT_ALIGN_RIGHT, max_size=8.4)
    draw_single_line(invoice_page, fitz.Rect(408, 643, 448, 654), calculation.sgst_amount, align=fitz.TEXT_ALIGN_RIGHT, max_size=8.4)
    draw_single_line(invoice_page, fitz.Rect(461, 643, 501, 654), calculation.tax_amount, align=fitz.TEXT_ALIGN_RIGHT, max_size=8.4)
    draw_single_line(invoice_page, fitz.Rect(130, 659, 500, 672), calculation.tax_amount_words, max_size=9.2, min_size=6.4)

    draw_single_line(eway_page, fitz.Rect(83, 65, 127, 76), calculation.formatted_date, align=fitz.TEXT_ALIGN_LEFT)
    draw_single_line(eway_page, fitz.Rect(141, 55, 217, 65), request.invoice_number, align=fitz.TEXT_ALIGN_LEFT, max_size=8.0, min_size=6.2)
    draw_single_line(eway_page, fitz.Rect(103, 180, 164, 190), request.eway_bill_number, align=fitz.TEXT_ALIGN_LEFT, max_size=8.0, min_size=6.2)
    draw_single_line(eway_page, fitz.Rect(286, 261, 360, 272), request.customer_name, fontname="helv", max_size=9.2)
    draw_multiline(eway_page, fitz.Rect(286, 321, 518, 344), request.customer_address, fontname="helv", max_size=8.4, min_size=6.2, max_lines=2)
    draw_single_line(eway_page, fitz.Rect(365, 418, 383, 429), str(request.bags), align=fitz.TEXT_ALIGN_RIGHT, max_size=8.6)
    draw_single_line(eway_page, fitz.Rect(429, 418, 477, 429), calculation.taxable_amount, align=fitz.TEXT_ALIGN_RIGHT, max_size=8.6)
    draw_single_line(eway_page, fitz.Rect(155, 649, 204, 660), calculation.taxable_amount, align=fitz.TEXT_ALIGN_RIGHT, max_size=8.6)
    draw_single_line(eway_page, fitz.Rect(252, 649, 292, 660), calculation.rounding_adjustment, align=fitz.TEXT_ALIGN_RIGHT, max_size=8.6)
    draw_single_line(eway_page, fitz.Rect(332, 663, 374, 674), calculation.sgst_amount, align=fitz.TEXT_ALIGN_RIGHT, max_size=8.6)
    draw_single_line(eway_page, fitz.Rect(163, 663, 204, 674), calculation.cgst_amount, align=fitz.TEXT_ALIGN_RIGHT, max_size=8.6)
    draw_single_line(eway_page, fitz.Rect(480, 649, 530, 660), calculation.total_amount, align=fitz.TEXT_ALIGN_RIGHT, max_size=8.6)

    pdf_bytes = output.tobytes(deflate=True, garbage=4)
    output.close()
    template.close()
    return pdf_bytes


app = FastAPI(title="Bill Editor Backend", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/bill/defaults")
def bill_defaults() -> dict[str, object]:
    template_pdf = resolve_template_pdf()
    return {
        "template_file": template_pdf.name,
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "defaults": DEFAULT_BILL.model_dump(mode="json"),
        "calculation": compute_bill(DEFAULT_BILL).model_dump(mode="json"),
    }


@app.post("/api/bill/render", response_model=BillRenderResponse)
def bill_render(request: BillRequest) -> BillRenderResponse:
    try:
        pdf_bytes = render_pdf(request)
        calculation = compute_bill(request)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Could not render the bill: {exc}") from exc

    return BillRenderResponse(
        file_name=build_file_name(request),
        pdf_base64=base64.b64encode(pdf_bytes).decode("ascii"),
        calculation=calculation,
    )
