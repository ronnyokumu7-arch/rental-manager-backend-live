class Quotation(Base):
    __tablename__ = "quotations"
    
    id = Column(Integer, primary_key=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"))
    client_id = Column(Integer, ForeignKey("clients.id"))
    vehicle_id = Column(Integer, ForeignKey("vehicles.id"))
    
    # Quotation specifics
    quotation_number = Column(String, unique=True)
    valid_until = Column(DateTime)
    status = Column(Enum(QuotationStatus))  # draft, sent, accepted, rejected, expired
    
    # Booking details (snapshot)
    start_date = Column(Date)
    end_date = Column(Date)
    total_amount = Column(Integer)
    currency_code = Column(String(3))
    
    # Sharing
    share_token = Column(String(36), unique=True)
    share_token_expires_at = Column(DateTime)
    sent_at = Column(DateTime)
    
    # Conversion
    booking_id = Column(Integer, ForeignKey("bookings.id"), nullable=True)
    converted_at = Column(DateTime, nullable=True)
    
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, onupdate=func.now())
