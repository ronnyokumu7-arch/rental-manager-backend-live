# backend/app/services/contract_pdf.py
from io import BytesIO
import os
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image
from sqlalchemy.orm import Session
from app.models.contracts import Contract
from app.models.bookings import Booking
from app.models.clients import Client
from app.models.vehicles import Vehicle
from app.models.tenants import Tenant
from app.models.tenant_profile import TenantProfile

def generate_contract_pdf(contract: Contract, db: Session) -> bytes:
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=20*mm, leftMargin=20*mm, topMargin=20*mm, bottomMargin=20*mm)
    
    # Fetch Data
    booking = db.query(Booking).filter(Booking.id == contract.booking_id).first()
    client = db.query(Client).filter(Client.id == booking.client_id).first() if booking else None
    vehicle = db.query(Vehicle).filter(Vehicle.id == booking.vehicle_id).first() if booking else None
    tenant = db.query(Tenant).filter(Tenant.id == contract.tenant_id).first()
    profile = db.query(TenantProfile).filter(TenantProfile.tenant_id == contract.tenant_id).first() if tenant else None

    styles = getSampleStyleSheet()
    brand_color = colors.HexColor("#1a1a2e")
    
    elements = []

    # --- HEADER ---
    elements.append(Paragraph("VEHICLE RENTAL AGREEMENT", ParagraphStyle('Title', fontSize=22, textColor=brand_color, alignment=1, spaceAfter=4)))
    elements.append(Paragraph(f"Contract No: {contract.contract_number}", ParagraphStyle('SubTitle', fontSize=12, textColor=colors.grey, alignment=1, spaceAfter=12)))
    elements.append(Spacer(1, 10*mm))

    # --- PARTIES ---
    parties_data = [
        ["LESSOR (Owner):", tenant.name if tenant else "—"],
        ["LESSEE (Renter):", client.full_name if client else "—"],
        ["Date:", contract.created_at.strftime("%d %B %Y") if contract.created_at else "—"],
    ]
    parties_table = Table(parties_data, colWidths=[50*mm, 100*mm])
    parties_table.setStyle(TableStyle([
        ('FONTNAME', (0,0), (0,-1), 'Helvetica-Bold'),
        ('FONTSIZE', (0,0), (-1,-1), 10),
        ('TEXTCOLOR', (0,0), (0,-1), colors.grey),
        ('BOTTOMPADDING', (0,0), (-1,-1), 8),
    ]))
    elements.append(parties_table)
    elements.append(Spacer(1, 10*mm))

    # --- VEHICLE DETAILS ---
    elements.append(Paragraph("<b>1. VEHICLE DETAILS</b>", styles['Heading2']))
    elements.append(Spacer(1, 4*mm))
    v_data = [
        ["Make/Model:", f"{vehicle.make} {vehicle.model}" if vehicle else "—"],
        ["Plate Number:", vehicle.plate_number if vehicle else "—"],
        ["Year:", str(vehicle.year) if vehicle else "—"],
    ]
    v_table = Table(v_data, colWidths=[50*mm, 100*mm])
    v_table.setStyle(TableStyle([
        ('FONTNAME', (0,0), (0,-1), 'Helvetica-Bold'),
        ('FONTSIZE', (0,0), (-1,-1), 10),
        ('TEXTCOLOR', (0,0), (0,-1), colors.grey),
        ('BOTTOMPADDING', (0,0), (-1,-1), 6),
    ]))
    elements.append(v_table)
    elements.append(Spacer(1, 10*mm))

    # --- TERMS (Simplified for example) ---
    elements.append(Paragraph("<b>2. TERMS AND CONDITIONS</b>", styles['Heading2']))
    terms_text = """
    1. The Lessee agrees to pay the Total Amount as specified in the associated invoice.<br/>
    2. The vehicle must be returned in the same condition as received.<br/>
    3. The Lessee is responsible for any damage or traffic fines incurred during the rental period.<br/>
    4. Late returns will be charged at 150% of the daily rate.<br/>
    """
    elements.append(Paragraph(terms_text, ParagraphStyle('Terms', fontSize=9, leading=14)))
    elements.append(Spacer(1, 15*mm))

    # --- SIGNATURES ---
    elements.append(Paragraph("<b>3. SIGNATURES</b>", styles['Heading2']))
    elements.append(Spacer(1, 10*mm))

    # Logic for Client Signature
    client_sig_cell = []
    if contract.signed_by_client and contract.signature_image_path and os.path.exists(contract.signature_image_path):
        # Render the actual signature image
        client_sig_cell.append(Image(contract.signature_image_path, width=40*mm, height=20*mm))
    else:
        # Render a line for physical signing
        client_sig_cell.append(Paragraph("_________________________", styles['Normal']))
    
    client_sig_cell.append(Paragraph(f"Client: {client.full_name if client else '—'}", ParagraphStyle('SigName', fontSize=8, textColor=colors.grey)))
    if contract.signed_by_client and contract.client_signed_at:
        client_sig_cell.append(Paragraph(f"Date: {contract.client_signed_at.strftime('%d %b %Y')}", ParagraphStyle('SigDate', fontSize=8, textColor=colors.grey)))

    # Logic for Lessor Signature (Placeholder for now)
    lessor_sig_cell = [
        Paragraph("_________________________", styles['Normal']),
        Paragraph(f"Representative: {tenant.name if tenant else '—'}", ParagraphStyle('SigName', fontSize=8, textColor=colors.grey)),
        Paragraph("Date: _______________", ParagraphStyle('SigDate', fontSize=8, textColor=colors.grey))
    ]

    sig_table = Table([[client_sig_cell, lessor_sig_cell]], colWidths=[80*mm, 80*mm])
    sig_table.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'BOTTOM'),
        ('TOPPADDING', (0,0), (-1,-1), 20),
    ]))
    elements.append(sig_table)

    doc.build(elements)
    return buffer.getvalue()
