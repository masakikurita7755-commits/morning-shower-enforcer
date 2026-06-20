import os
import requests
import logging
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class PayPalClient:
    def __init__(self):
        self.mode = os.getenv("PAYPAL_MODE", "sandbox").lower()
        self.client_id = os.getenv("PAYPAL_CLIENT_ID")
        self.client_secret = os.getenv("PAYPAL_CLIENT_SECRET")
        
        # Determine base URL based on mode
        if self.mode == "live":
            self.base_url = "https://api-m.paypal.com"
        else:
            self.base_url = "https://api-m.sandbox.paypal.com"

    def is_configured(self):
        """Checks if Client ID and Secret are configured."""
        return bool(self.client_id and self.client_secret and 
                    "YOUR_PAYPAL" not in self.client_id)

    def get_access_token(self):
        """
        Retrieves an OAuth2 Access Token from PayPal API.
        """
        if not self.is_configured():
            raise ValueError("PayPal Client ID and Secret are not configured in environment variables.")

        url = f"{self.base_url}/v1/oauth2/token"
        headers = {
            "Accept": "application/json",
            "Accept-Language": "en_US",
        }
        data = {
            "grant_type": "client_credentials"
        }
        
        logger.info("Requesting access token from PayPal...")
        response = requests.post(
            url, 
            headers=headers, 
            data=data, 
            auth=(self.client_id, self.client_secret),
            timeout=10
        )
        
        if response.status_code == 200:
            token_data = response.json()
            return token_data.get("access_token")
        else:
            raise Exception(f"Failed to get Access Token: {response.status_code} - {response.text}")

    def create_order(self, amount, currency="USD"):
        """
        Creates a PayPal Order.
        Returns: order_id, approve_url
        """
        token = self.get_access_token()
        url = f"{self.base_url}/v2/checkout/orders"
        
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
        }
        
        payload = {
            "intent": "CAPTURE",
            "purchase_units": [
                {
                    "amount": {
                        "currency_code": currency,
                        "value": str(amount)
                    },
                    "description": "Morning Shower Enforcer - Fine for missed shower"
                }
            ],
            "application_context": {
                "return_url": "http://localhost:8501/?status=success",
                "cancel_url": "http://localhost:8501/?status=cancel",
                "shipping_preference": "NO_SHIPPING",
                "user_action": "PAY_NOW"
            }
        }
        
        logger.info(f"Creating PayPal Order for {amount} {currency}...")
        response = requests.post(url, headers=headers, json=payload, timeout=10)
        
        if response.status_code in [200, 201]:
            order_data = response.json()
            order_id = order_data.get("id")
            
            # Extract approve URL
            approve_url = None
            for link in order_data.get("links", []):
                if link.get("rel") == "approve":
                    approve_url = link.get("href")
                    break
                    
            logger.info(f"Order created successfully: ID={order_id}")
            return order_id, approve_url
        else:
            raise Exception(f"Failed to create order: {response.status_code} - {response.text}")

    def capture_order(self, order_id):
        """
        Captures (executes) the created order.
        In a manual flow, this runs AFTER the user approves the payment via the approve_url.
        """
        token = self.get_access_token()
        url = f"{self.base_url}/v2/checkout/orders/{order_id}/capture"
        
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
        }
        
        logger.info(f"Capturing PayPal Order ID: {order_id}...")
        response = requests.post(url, headers=headers, json={}, timeout=10)
        
        if response.status_code in [200, 201]:
            capture_data = response.json()
            status = capture_data.get("status")
            logger.info(f"Order captured: Status={status}")
            return capture_data
        else:
            raise Exception(f"Failed to capture order: {response.status_code} - {response.text}")

    def charge_fine_sandbox(self, amount, currency="USD"):
        """
        High-level wrapper to charge the fine.
        If PayPal credentials are set:
           - Creates an Order.
           - Returns (success=True, order_id, approve_url, is_mock=False)
           - Note: Since standard sandbox Orders require user redirect to approve, we return the approve_url.
        If NOT configured (fallback/demo mode):
           - Simulates a payment.
           - Returns (success=True, order_id="MOCK-XXXX", approve_url=None, is_mock=True)
        """
        if not self.is_configured():
            logger.warning("PayPal credentials not set! Simulating transaction in DEMO Mode.")
            return {
                "success": True,
                "order_id": "MOCK-ORDER-12345",
                "status": "COMPLETED",
                "message": f"[DEMO MODE] Charged fine of {amount} {currency} to user.",
                "is_mock": True
            }
            
        try:
            order_id, approve_url = self.create_order(amount, currency)
            return {
                "success": True,
                "order_id": order_id,
                "approve_url": approve_url,
                "status": "CREATED",
                "message": f"PayPal Order created. Complete authorization at: {approve_url}",
                "is_mock": False
            }
        except Exception as e:
            logger.error(f"PayPal execution failed: {e}")
            return {
                "success": False,
                "message": f"PayPal Error: {str(e)}",
                "is_mock": False
            }
            
    def execute_automatic_billing_agreement_charge_concept(self, agreement_id, amount, currency="USD"):
        """
        Concept function for automatic charges (no user approval required at time of fine).
        This requires pre-authorization via Reference Transactions or Subscriptions.
        
        Endpoint: /v1/payments/billing-agreements/<agreement_id>/reference-transactions
        (Legacy v1 Billing Agreement Reference Transactions, or the new Vault Payment Tokens API)
        """
        token = self.get_access_token()
        # Example using PayPal reference transaction / vault token
        # This is a conceptual implementation of how it would run without user redirect:
        url = f"{self.base_url}/v1/payments/billing-agreements/{agreement_id}/reference-transactions"
        
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
        }
        
        payload = {
            "amount": {
                "currency": currency,
                "value": str(amount)
            },
            "description": "Morning Shower Enforcer - Automated Fine"
        }
        
        # response = requests.post(url, headers=headers, json=payload)
        pass
