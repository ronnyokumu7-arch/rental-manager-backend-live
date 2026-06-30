# Endpoints:
POST   /quotations/                    # Create quotation
GET    /quotations/                    # List quotations
GET    /quotations/{id}                # Get quotation
POST   /quotations/{id}/send           # Send to client
POST   /quotations/{id}/convert        # Convert to booking
DELETE /quotations/{id}                # Cancel quotation

GET    /quotations/public/{token}      # Public view
POST   /quotations/public/{token}/accept # Client accepts
