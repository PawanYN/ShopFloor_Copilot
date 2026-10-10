"""A mock of the plant's work-order system. A real deployment would query the ERP here."""

# The IDs match the parts in data/images, so a photo and its work order can be tried together.
WORK_ORDERS = {
    "WO-19651": {"status": "in inspection", "part": "BP-120 bracket plate", "rework_count": 0, "priority": False},
    "WO-89448": {"status": "in inspection", "part": "BP-120 bracket plate", "rework_count": 0, "priority": False},
    "WO-64962": {"status": "in rework", "part": "BP-120 bracket plate", "rework_count": 1, "priority": False},
    "WO-47051": {"status": "in inspection", "part": "BP-120 bracket plate", "rework_count": 0, "priority": True},
    "WO-81451": {"status": "on hold", "part": "BP-120 bracket plate", "rework_count": 0, "priority": False},
    "WO-45280": {"status": "closed", "part": "BP-120 bracket plate", "rework_count": 0, "priority": False},
}


def check_work_order_status(work_order_id: str) -> dict:
    record = WORK_ORDERS.get(work_order_id.strip().upper())
    if record is None:
        return {"work_order_id": work_order_id, "found": False}
    return {"work_order_id": work_order_id.strip().upper(), "found": True, **record}
