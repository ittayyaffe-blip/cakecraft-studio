from app.core.database import supabase
from app.services.designer_service import get_designer_options
from app.services.template_service import get_template_by_id


def _find_option(options: dict, key: str, option_id: str) -> dict | None:
    return next((item for item in options[key] if item["id"] == option_id), None)


def _find_or_create_customer(name: str, phone: str, email: str) -> str:
    existing = (
        supabase.table("customers").select("id").eq("email", email).limit(1).execute()
    )
    if existing.data:
        return existing.data[0]["id"]

    created = (
        supabase.table("customers")
        .insert({"name": name, "phone": phone, "email": email})
        .execute()
    )
    return created.data[0]["id"]


def create_order(order: dict) -> str | None:
    template = get_template_by_id(order["template_id"])
    if template is None:
        return None

    options = get_designer_options()
    cake_size = _find_option(options, "cake_sizes", order["cake_size_id"])
    flavor = _find_option(options, "flavors", order["flavor_id"])
    filling = _find_option(options, "fillings", order["filling_id"])
    frosting = _find_option(options, "frostings", order["frosting_id"])

    if not all([cake_size, flavor, filling, frosting]):
        raise ValueError("Invalid cake size, flavor, filling, or frosting selection")

    total_price = template["base_price"] + cake_size["price_adjustment"]

    customer_id = _find_or_create_customer(
        order["customer_name"], order["customer_phone"], order["customer_email"]
    )

    configuration = {
        "cakeSize": cake_size,
        "flavor": flavor,
        "filling": filling,
        "frosting": frosting,
    }

    response = (
        supabase.table("orders")
        .insert(
            {
                "customer_id": customer_id,
                "template_id": order["template_id"],
                "status": "pending",
                "total_price": total_price,
                "configuration": configuration,
                "notes": order["notes"],
            }
        )
        .execute()
    )
    return response.data[0]["id"]
