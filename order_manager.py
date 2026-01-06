"""
Order Manager with Webhook Support

Manages Planet orders with webhook notifications for completion status.
"""

import json
import logging
import asyncio
from typing import Dict, Any, Optional
from pathlib import Path
from datetime import datetime

from planet import Planet

logger = logging.getLogger(__name__)


class OrderManager:
    """Manages Planet orders with status tracking and webhook support."""
    
    def __init__(self):
        self.pl = Planet()
        # Use current working directory instead of hardcoded path
        self.orders_file = Path.cwd() / "orders_status.json"
        self._ensure_orders_file()
    
    def _ensure_orders_file(self):
        """Ensure orders status file exists."""
        if not self.orders_file.exists():
            self._save_orders({})
    
    def _load_orders(self) -> Dict[str, Any]:
        """Load orders from status file."""
        try:
            with open(self.orders_file, 'r') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error loading orders: {e}")
            return {}
    
    def _save_orders(self, orders: Dict[str, Any]):
        """Save orders to status file."""
        try:
            with open(self.orders_file, 'w') as f:
                json.dump(orders, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving orders: {e}")
    
    def create_order_with_tracking(
        self,
        item_ids: list,
        item_type: str,
        asset_type: str,
        aoi: Dict[str, Any],
        order_name: Optional[str] = None,
        enable_webhook: bool = False,
        webhook_url: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Create an order with tracking.
        
        Args:
            item_ids: List of item IDs
            item_type: Item type (e.g., "PSScene")
            asset_type: Asset type
            aoi: AOI geometry for clipping
            order_name: Optional order name
            enable_webhook: Whether to enable webhook notifications
            webhook_url: Optional webhook URL
            
        Returns:
            Dictionary with order creation status
        """
        try:
            from planet import order_request
            
            if order_name is None:
                order_name = f"geovision_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            
            # Map asset_type to product_bundle
            product_bundle = self._get_product_bundle(asset_type)
            
            # Build notifications
            notifications = {"email": True}
            if enable_webhook and webhook_url:
                notifications["webhook"] = {
                    "url": webhook_url,
                    "per_order": True
                }
            
            # Build order request
            request = order_request.build_request(
                name=order_name,
                products=[
                    order_request.product(
                        item_ids=item_ids,
                        product_bundle=product_bundle,
                        item_type=item_type
                    )
                ],
                tools=[
                    {
                        "clip": {
                            "aoi": aoi
                        }
                    }
                ],
                notifications=notifications
            )
            
            # Create order
            order = self.pl.orders.create_order(request)
            order_id = order["id"]
            
            # Track order
            orders = self._load_orders()
            orders[order_id] = {
                "order_name": order_name,
                "item_ids": item_ids,
                "item_count": len(item_ids),
                "created_at": datetime.now().isoformat(),
                "state": "queued",
                "webhook_enabled": enable_webhook
            }
            self._save_orders(orders)
            
            logger.info(f"Created and tracking order {order_id}")
            return {
                "status": "created",
                "order_id": order_id,
                "order_name": order_name,
                "item_count": len(item_ids),
                "message": "Order created successfully. Processing may take 5-15 minutes."
            }
        
        except Exception as e:
            logger.error(f"Order creation error: {e}", exc_info=True)
            return {"error": str(e)}
    
    def _get_product_bundle(self, asset_type: str) -> str:
        """
        Convert asset type to product bundle.

        Asset types (from search results) need to be mapped to product bundles (for Orders API).
        See: https://developers.planet.com/docs/orders/product-bundles-reference/

        If asset_type is not in the mapping, it's passed through as-is
        (in case it's already a product bundle or a new asset type).
        """
        asset_to_bundle = {
            # 4-band analytic
            "ortho_analytic_4b": "analytic_udm2",
            "ortho_analytic_4b_sr": "analytic_sr_udm2",
            # 8-band analytic
            "ortho_analytic_8b": "analytic_8b_udm2",
            "ortho_analytic_8b_sr": "analytic_8b_sr_udm2",
            # Visual
            "ortho_visual": "visual",
            # Basic (non-orthorectified)
            "basic_analytic_4b": "analytic_udm2",
            "basic_analytic_8b": "analytic_8b_udm2",
        }

        # Return mapped value, or pass through if not found (might be a bundle name already)
        return asset_to_bundle.get(asset_type, asset_type)
    
    def check_order_status(self, order_id: str) -> Dict[str, Any]:
        """
        Check order status and update tracking.
        
        Args:
            order_id: Order ID to check
            
        Returns:
            Dictionary with order status
        """
        try:
            order = self.pl.orders.get_order(order_id)
            state = order.get("state")
            
            # Update tracked orders
            orders = self._load_orders()
            if order_id in orders:
                orders[order_id]["state"] = state
                orders[order_id]["last_checked"] = datetime.now().isoformat()
                self._save_orders(orders)
            
            logger.info(f"Order {order_id} state: {state}")
            return {
                "order_id": order_id,
                "state": state,
                "created_on": order.get("created_on"),
                "last_modified": order.get("last_modified"),
                "is_complete": state in ["success", "partial", "failed"]
            }
        
        except Exception as e:
            logger.error(f"Error checking order status: {e}")
            return {"error": str(e)}
    
    def get_pending_orders(self) -> list:
        """Get list of pending orders."""
        orders = self._load_orders()
        pending = []
        
        for order_id, info in orders.items():
            if info.get("state") not in ["success", "partial", "failed"]:
                status = self.check_order_status(order_id)
                if not status.get("is_complete"):
                    pending.append({
                        "order_id": order_id,
                        "order_name": info["order_name"],
                        "state": info["state"],
                        "created_at": info["created_at"]
                    })
        
        return pending
    
    async def wait_for_order(
        self,
        order_id: str,
        timeout: int = 1800,  # 30 minutes
        check_interval: int = 30  # 30 seconds
    ) -> Dict[str, Any]:
        """
        Wait for order to complete with periodic status checks.
        
        Args:
            order_id: Order ID to wait for
            timeout: Maximum wait time in seconds
            check_interval: Status check interval in seconds
            
        Returns:
            Dictionary with final order status
        """
        start_time = datetime.now()
        
        while True:
            status = self.check_order_status(order_id)
            
            if status.get("error"):
                return status
            
            if status.get("is_complete"):
                return status
            
            # Check timeout
            elapsed = (datetime.now() - start_time).total_seconds()
            if elapsed > timeout:
                return {
                    "error": "Order wait timeout",
                    "order_id": order_id,
                    "state": status.get("state")
                }
            
            # Wait before next check
            await asyncio.sleep(check_interval)
            logger.info(f"Waiting for order {order_id}... ({int(elapsed)}s elapsed)")
    
    def download_order(self, order_id: str) -> Dict[str, Any]:
        """
        Download completed order.
        
        Args:
            order_id: Order ID to download
            
        Returns:
            Dictionary with download status
        """
        try:
            # Use current working directory instead of hardcoded path
            download_dir = Path.cwd() / "downloads"
            download_dir.mkdir(exist_ok=True)
            
            # Check if order is complete
            status = self.check_order_status(order_id)
            if not status.get("is_complete"):
                return {
                    "error": "Order not yet complete",
                    "state": status.get("state")
                }
            
            logger.info(f"Downloading order {order_id}")
            
            # Download order
            paths = self.pl.orders.download_order(
                order_id,
                directory=str(download_dir),
                overwrite=True
            )
            
            # Update tracking
            orders = self._load_orders()
            if order_id in orders:
                orders[order_id]["downloaded_at"] = datetime.now().isoformat()
                orders[order_id]["file_count"] = len(paths)
                self._save_orders(orders)
            
            logger.info(f"Downloaded {len(paths)} files for order {order_id}")
            return {
                "status": "success",
                "order_id": order_id,
                "file_count": len(paths),
                "files": [str(p) for p in paths]
            }
        
        except Exception as e:
            logger.error(f"Order download error: {e}", exc_info=True)
            return {"error": str(e)}


# Global instance
order_manager = OrderManager()
