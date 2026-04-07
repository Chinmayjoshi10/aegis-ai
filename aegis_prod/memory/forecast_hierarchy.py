# aegis_ai/aegis_ai/memory/forecast_hierarchy.py

"""
Defines physical roll-up constraints for enterprise forecasts.

This tells AEGIS how bottom-level entities roll up into totals.
All forecasts will be forced to obey these constraints.
"""

FORECAST_HIERARCHY = {

    # Example: Port supply must equal sum of warehouses
    "PORT_TOTAL": [
        "Warehouse_A",
        "Warehouse_B",
        "Warehouse_C",
    ],

    # You can extend later:
    # "NATIONAL_TOTAL": ["PORT_TOTAL", "RAIL_TOTAL"]
}
