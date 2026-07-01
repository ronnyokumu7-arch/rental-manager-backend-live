from io import BytesIO
from datetime import datetime, timezone
from decimal import Decimal
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from sqlalchemy.orm import Session
from app.models.invoices import Invoice
from app.models.contracts import Contract
from app.models.quotations import Quotation
from app.models.tenants import Tenant
from app.models.tenant_profile import TenantProfile
from app.models.tenant_policies import TenantPolicy
from app.models.bookings import Booking
from app.models.clients import Client
from app.models.vehicles import Vehicle

def generate_invoice_pdf(invoice: Invoice, db: Session) -> bytes:
    # ... (keep your existing generate_invoice_pdf code)
    pass  # I'm omitting it to save space, keep your existing code

def generate_contract_pdf(contract: Contract, db: Session) -> bytes:
    """Generate a professional contract PDF"""
    from reportlab.lib.units import cm
    
    booking = db.query(Booking).filter(Booking.id == contract.booking_id).first()
    client = db.query(Client).filter(Client.id == booking.client_id).first() if booking else None
    vehicle = db.query(Vehicle).filter(Vehicle.id == booking.vehicle_id).first() if booking else None
    tenant = db.query(Tenant).filter(Tenant.id == contract.tenant_id).first()
    
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=20 * mm,
        leftMargin=20 * mm,
        topMargin=20 * mm,
        bottomMargin=20 * mm,
    )
    
    styles = getSampleStyleSheet()
    brand_color = colors.HexColor("#1a1a2e")
    accent_color = colors.HexColor("#4f8cff")
    
    title_style = ParagraphStyle("Title", parent=styles["Heading1"], fontSize=24, textColor=brand_color, spaceAfter=4)
    small_style = ParagraphStyle("Small", parent=styles["Normal"], fontSize=9, textColor=colors.HexColor("#555555"))
    
    elements = []
    
    # Header
    elements.append(Paragraph("VEHICLE RENTAL CONTRACT", title_style))
    elements.append(Paragraph(f"Contract No: {contract.contract_number}", 
                             ParagraphStyle("ContractNum", parent=styles["Normal"], fontSize=13, textColor=accent_color, spaceAfter=16)))
    
    # Parties
    elements.append(Paragraph("<b>Parties to the Agreement</b>", styles["Heading2"]))
    elements.append(Spacer(1, 5))
    
    parties_data = [
        ["Lessor (Owner):", tenant.name if tenant else "—"],
        ["Lessee (Renter):", client.full_name if client else "—"],
        ["Contract Date:", contract.created_at.strftime("%d %b %Y") if contract.created_at else "—"],
    ]
    
    parties_table = Table(parties_data, colWidths=[50 * mm, 90 * mm])
    parties_table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("TEXTCOLOR", (0, 0), (0, -1), colors.HexColor("#888888")),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    elements.append(parties_table)
    elements.append(Spacer(1, 10 * mm))
    
    # Vehicle Details
    elements.append(Paragraph("<b>Vehicle Details</b>", styles["Heading2"]))
    elements.append(Spacer(5))
    
    vehicle_data = [
        ["Make & Model:", f"{vehicle.make} {vehicle.model}" if vehicle else "—"],
        ["Plate Number:", vehicle.plate_number if vehicle else "—"],
        ["Year:", str(vehicle.year) if vehicle else "—"],
    ]
    
    vehicle_table = Table(vehicle_data, colWidths=[50 * mm, 90 * mm])
    vehicle_table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("TEXTCOLOR", (0, 0), (0, -1), colors.HexColor("#888888")),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    elements.append(vehicle_table)
    elements.append(Spacer(1, 10 * mm))
    
    # Rental Period
    elements.append(Paragraph("<b>Rental Period</b>", styles["Heading2"]))
    elements.append(Spacer(5))
    
    period_data = [
        ["Start Date:", booking.start_date.strftime("%d %B %Y") if booking else "—"],
        ["End Date:", booking.end_date.strftime("%d %B %Y") if booking else "—"],
        ["Duration:", f"{(booking.end_date - booking.start_date).days} days" if booking else "—"],
        ["Pickup Location:", booking.pickup_location or "—" if booking else "—"],
        ["Return Location:", booking.return_location or "—" if booking else "—"],
    ]
    
    period_table = Table(period_data, colWidths=[50 * mm, 90 * mm])
    period_table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("TEXTCOLOR", (0, 0), (0, -1), colors.HexColor("#888888")),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    elements.append(period_table)
    elements.append(Spacer(1, 10 * mm))
    
    # Financial Terms
    elements.append(Paragraph("<b>Financial Terms</b>", styles["Heading2"]))
    elements.append(Spacer(5))
    
    financial_data = [
        ["Total Amount:", f"{booking.currency_code} {booking.total_amount:,.2f}" if booking else "—"],
        ["Currency:", booking.currency_code if booking else "—"],
    ]
    
    financial_table = Table(financial_data, colWidths=[50 * mm, 90 * mm])
    financial_table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("TEXTCOLOR", (0, 0), (0, -1), colors.HexColor("#888888")),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    elements.append(financial_table)
    elements.append(Spacer(1, 15 * mm))
    
    # Terms and Conditions
    elements.append(Paragraph("<b>Terms and Conditions</b>", styles["Heading2"]))
    elements.append(Spacer(1, 5))
    
    terms_text = """
    1. The Lessee agrees to pay the Total Amount as specified above.<br/>
    2. The vehicle must be returned in the same condition as received, normal wear and tear excepted.<br/>
    3. The Lessee is responsible for any damage to the vehicle during the rental period.<br/>
    4. Late returns will be charged at the daily rate.<br/>
    5. The Lessor reserves the right to terminate this agreement if terms are violated.<br/>
    6. This contract is governed by the laws of Kenya.
    """
    
    elements.append(Paragraph(terms_text, small_style))
    elements.append(Spacer(1, 10 * mm))
    
    # Signature Section
    elements.append(Paragraph("<b>Signatures</b>", styles["Heading2"]))
    elements.append(Spacer(1, 10))
    
    signature_data = [
        ["Lessor Signature:", "_________________________", "Date: _______________"],
        ["Lessee Signature:", "_________________________", "Date: _______________"],
    ]
    
    signature_table = Table(signature_data, colWidths=[40 * mm, 50 * mm, 50 * mm])
    signature_table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    elements.append(signature_table)
    
    elements.append(Spacer(1, 10 * mm))
    elements.append(Paragraph(f"Generated on {datetime.now(timezone.utc).strftime('%d %b %Y %H:%M')} UTC", small_style))
    
    doc.build(elements)
    return buffer.getvalue()
        


# ... (keep existing generate_invoice_pdf and generate_contract_pdf) ...

def generate_quotation_pdf(quotation: Quotation, db: Session) -> bytes:
    """Generate a professional Quotation PDF"""
    client = db.query(Client).filter(Client.id == quotation.client_id).first()
    vehicle = db.query(Vehicle).filter(Vehicle.id == quotation.vehicle_id).first()
    tenant = db.query(Tenant).filter(Tenant.id == quotation.tenant_id).first()

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4, rightMargin=20*mm, leftMargin=20*mm, topMargin=20*mm, bottomMargin=20*mm,
    )
    styles = getSampleStyleSheet()
    brand_color = colors.HexColor("#1a1a2e")
    accent_color = colors.HexColor("#4f8cff")

    title_style = ParagraphStyle("Title", parent=styles["Heading1"], fontSize=24, textColor=brand_color, spaceAfter=4)
    small_style = ParagraphStyle("Small", parent=styles["Normal"], fontSize=9, textColor=colors.HexColor("#555555"))
    elements = []

    # Header
    elements.append(Paragraph("VEHICLE RENTAL QUOTATION", title_style))
    elements.append(Paragraph(f"Quote Ref: #{quotation.id}", 
                             ParagraphStyle("Ref", parent=styles["Normal"], fontSize=13, textColor=accent_color, spaceAfter=16)))

    # Parties
    elements.append(Paragraph("<b>Prepared For</b>", styles["Heading2"]))
    parties_data = [
        ["Client:", client.full_name if client else "—"],
        ["Date:", quotation.created_at.strftime("%d %b %Y") if quotation.created_at else "—"],
        ["Valid Until:", quotation.share_token_expires_at.strftime("%d %b %Y") if quotation.share_token_expires_at else "—"],
    ]
    parties_table = Table(parties_data, colWidths=[40*mm, 100*mm])
    parties_table.setStyle(TableStyle([
        ("FONTNAME", (0,0), (-1,-1), "Helvetica"), ("FONTSIZE", (0,0), (-1,-1), 10),
        ("FONTNAME", (0,0), (0,-1), "Helvetica-Bold"), ("TEXTCOLOR", (0,0), (0,-1), colors.HexColor("#888888")),
        ("TOPPADDING", (0,0), (-1,-1), 4), ("BOTTOMPADDING", (0,0), (-1,-1), 4),
    ]))
    elements.append(parties_table)
    elements.append(Spacer(1, 10*mm))

    # Vehicle & Trip Details
    elements.append(Paragraph("<b>Quotation Details</b>", styles["Heading2"]))
    details_data = [
        ["Vehicle:", f"{vehicle.make} {vehicle.model} ({vehicle.plate_number})" if vehicle else "—"],
        ["Pickup:", quotation.pickup_location or "—"],
        ["Return:", quotation.return_location or "—"],
        ["Destination:", quotation.destination or "—"],
        ["Start Date:", quotation.start_date.strftime("%d %B %Y")],
        ["End Date:", quotation.end_date.strftime("%d %B %Y")],
    ]
    details_table = Table(details_data, colWidths=[40*mm, 100*mm])
    details_table.setStyle(TableStyle([
        ("FONTNAME", (0,0), (-1,-1), "Helvetica"), ("FONTSIZE", (0,0), (-1,-1), 10),
        ("FONTNAME", (0,0), (0,-1), "Helvetica-Bold"), ("TEXTCOLOR", (0,0), (0,-1), colors.HexColor("#888888")),
        ("TOPPADDING", (0,0), (-1,-1), 4), ("BOTTOMPADDING", (0,0), (-1,-1), 4),
    ]))
    elements.append(details_table)
    elements.append(Spacer(1, 15*mm))

    # Financials
    elements.append(Paragraph("<b>Financial Summary</b>", styles["Heading2"]))
    financial_data = [
        ["Daily Rate:", f"{quotation.currency_code} {quotation.daily_rate:,.2f}" if quotation.daily_rate else "—"],
        ["Total Amount:", f"{quotation.currency_code} {quotation.total_amount:,.2f}"],
    ]
    financial_table = Table(financial_data, colWidths=[40*mm, 100*mm])
    financial_table.setStyle(TableStyle([
        ("FONTNAME", (0,0), (-1,-1), "Helvetica"), ("FONTSIZE", (0,0), (-1,-1), 10),
        ("FONTNAME", (0,0), (0,-1), "Helvetica-Bold"), ("TEXTCOLOR", (0,0), (0,-1), colors.HexColor("#888888")),
        ("TOPPADDING", (0,0), (-1,-1), 4), ("BOTTOMPADDING", (0,0), (-1,-1), 4),
    ]))
    elements.append(financial_table)
    elements.append(Spacer(1, 15*mm))

    # Terms
    if quotation.terms_and_conditions:
        elements.append(Paragraph("<b>Terms & Conditions</b>", styles["Heading2"]))
        elements.append(Paragraph(quotation.terms_and_conditions.replace('\n', '<br/>'), small_style))
        elements.append(Spacer(1, 10*mm))

    elements.append(Paragraph(f"Generated by {tenant.name if tenant else 'Rental Manager'}", small_style))
    doc.build(elements)
    return buffer.getvalue()
