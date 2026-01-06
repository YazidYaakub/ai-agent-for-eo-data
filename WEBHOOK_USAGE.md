# Webhook Notification Usage Guide

## Overview

GeoVision AI supports webhook notifications for Planet Orders API. When you create a clip order with a webhook URL, Planet will send a notification to that endpoint when your order is ready for download.

## How It Works

1. **Create Order with Webhook**: When creating a clip order, provide a `webhook_url` parameter
2. **Planet Processes Order**: Planet processes your imagery order (typically 5-15 minutes)
3. **Webhook Notification Sent**: When the order is ready, Planet sends a POST request to your webhook URL
4. **Download Ready**: You can then download the completed order using the `download_order` tool

## Setting Up a Webhook Endpoint

### Requirements

Your webhook endpoint must:
- Accept HTTP POST requests
- Be publicly accessible (https://your-domain.com/webhook)
- Respond with HTTP 200 status code to acknowledge receipt
- Handle JSON payload from Planet

### Example Webhook Server (Python/Flask)

```python
from flask import Flask, request, jsonify
import logging

app = Flask(__name__)
logger = logging.getLogger(__name__)

@app.route('/planet-webhook', methods=['POST'])
def planet_webhook():
    """Handle Planet Orders API webhook notifications."""
    try:
        payload = request.get_json()

        # Log the notification
        logger.info(f"Received webhook: {payload}")

        # Extract order information
        order_id = payload.get('order_id')
        state = payload.get('state')

        # Process based on order state
        if state == 'success':
            logger.info(f"Order {order_id} completed successfully!")
            # Trigger download or notify user

        elif state == 'failed':
            logger.error(f"Order {order_id} failed!")

        # Acknowledge receipt
        return jsonify({"status": "received"}), 200

    except Exception as e:
        logger.error(f"Webhook error: {e}")
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
```

### Quick Testing with ngrok

For local development, use [ngrok](https://ngrok.com/) to expose your local server:

```bash
# Start your webhook server locally
python webhook_server.py

# In another terminal, start ngrok
ngrok http 5000

# Use the ngrok URL (e.g., https://abc123.ngrok.io/planet-webhook) as your webhook_url
```

## Using Webhooks in GeoVision AI

### Via Chat Interface

When the agent creates an order, you can specify a webhook URL:

```
User: "Download the first 3 results as clipped imagery and notify me at https://my-server.com/webhook"
```

The agent will extract the webhook URL from your message and pass it to the `create_clip_order` function.

### Via Agent Function (Direct)

```python
from geovision_agents import create_clip_order

# Create order with webhook notification
result = create_clip_order(
    item_ids=["20260101_034626_26_24d8"],
    item_type="PSScene",
    asset_type="ortho_analytic_8b_sr",
    aoi_json='{"type": "Polygon", "coordinates": [...]}',
    order_name="my_order",
    webhook_url="https://my-server.com/webhook"
)
```

## Webhook Payload Structure

Planet sends a JSON payload with the following structure:

### Success Notification

```json
{
  "order_id": "abc123-def456-ghi789",
  "state": "success",
  "created_on": "2026-01-05T10:30:00Z",
  "last_modified": "2026-01-05T10:45:00Z",
  "name": "geovision_20260105_103000",
  "_links": {
    "self": "https://api.planet.com/compute/ops/orders/v2/abc123-def456-ghi789",
    "results": [
      {
        "name": "20260101_034626_26_24d8_3B_AnalyticMS_SR_clip.tif",
        "location": "https://api.planet.com/compute/ops/download/...",
        "expires_at": "2026-01-12T10:45:00Z"
      }
    ]
  }
}
```

### Failed Notification

```json
{
  "order_id": "abc123-def456-ghi789",
  "state": "failed",
  "error_hints": [
    "Insufficient quota for requested assets"
  ],
  "created_on": "2026-01-05T10:30:00Z",
  "last_modified": "2026-01-05T10:45:00Z"
}
```

### Partial Success Notification

```json
{
  "order_id": "abc123-def456-ghi789",
  "state": "partial",
  "created_on": "2026-01-05T10:30:00Z",
  "last_modified": "2026-01-05T10:45:00Z",
  "_links": {
    "results": [
      {
        "name": "scene1.tif",
        "location": "https://..."
      }
    ]
  },
  "error_hints": [
    "Some items could not be processed"
  ]
}
```

## Webhook States

| State | Description | Action |
|-------|-------------|--------|
| `queued` | Order accepted and queued | Wait |
| `running` | Order is being processed | Wait |
| `success` | Order completed successfully | Download files |
| `failed` | Order failed completely | Check error_hints |
| `partial` | Some items succeeded, some failed | Download available files, check errors |
| `cancelled` | Order was cancelled | No action needed |

## Best Practices

1. **Security**:
   - Use HTTPS for webhook endpoints
   - Validate the webhook payload source
   - Implement request signature verification if needed

2. **Reliability**:
   - Respond with HTTP 200 quickly (< 3 seconds)
   - Process the webhook asynchronously (queue the work)
   - Handle duplicate notifications gracefully

3. **Error Handling**:
   - Log all webhook payloads for debugging
   - Implement retry logic for failed processing
   - Monitor webhook endpoint health

4. **Testing**:
   - Test with ngrok during development
   - Use Planet's test orders for validation
   - Monitor logs for webhook delivery issues

## Alternative: Email Notifications

If you don't set up a webhook, Planet will still send email notifications to your account email address when orders complete. However, webhooks enable:
- Automated download workflows
- Real-time processing
- Integration with your systems

## Troubleshooting

### Webhook Not Received

1. Check webhook endpoint is publicly accessible
2. Verify webhook URL is correct in order creation logs
3. Check Planet API logs for delivery attempts
4. Ensure endpoint returns HTTP 200

### Order Status Check Without Webhook

If webhook isn't working, you can poll order status:

```
User: "Check status of order abc123-def456-ghi789"
```

The agent will use `check_order_status` to get current order state.

## Code Reference

- **Create order with webhook**: `geovision_agents.py` - `create_clip_order()` function
- **Order management**: `order_manager.py` - `OrderManager` class
- **Webhook parameter**: `order_manager.py:51-110` - `create_order_with_tracking()` method

## Further Reading

- [Planet Orders API Documentation](https://developers.planet.com/docs/orders/)
- [Planet Webhook Notifications](https://developers.planet.com/docs/orders/notifications/)
- [ngrok Documentation](https://ngrok.com/docs)
