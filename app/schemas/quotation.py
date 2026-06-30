class QuotationOut(BaseModel):
    id: int
    quotation_number: str
    status: QuotationStatus
    client_name: str
    vehicle_details: str
    start_date: date
    end_date: date
    total_amount: int
    valid_until: datetime
    share_token: Optional[str] = None
    booking_id: Optional[int] = None
    created_at: datetime
