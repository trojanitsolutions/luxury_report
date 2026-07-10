#!/usr/bin/env python3
"""Quick integration test for Sales Person Wise Sales report."""

import sys
import os

# Add bench to path
sys.path.insert(0, '/home/trojan-technologies/frappe-bench')
os.chdir('/home/trojan-technologies/frappe-bench')

def run_test():
    """Run basic integration tests."""
    try:
        # Import modules
        print("Testing module imports...")
        from luxury_report.luxury_report.report.sales_person_wise_sales.queries import (
            build_common_conditions, get_so_totals, get_si_totals, get_dn_totals
        )
        print("  ✓ queries module imports")

        from luxury_report.luxury_report.report.sales_person_wise_sales.analytics import (
            build_main_table, build_kpis, build_extra_charts
        )
        print("  ✓ analytics module imports")

        from luxury_report.luxury_report.report.sales_person_wise_sales.excel_export import (
            download_excel
        )
        print("  ✓ excel_export module imports")

        from luxury_report.luxury_report.report.sales_person_wise_sales.sales_person_wise_sales import (
            execute, get_dashboard_data, get_columns
        )
        print("  ✓ main report module imports")

        # Test basic data structures
        print("\nTesting data structures...")
        cols = get_columns()
        assert isinstance(cols, list), "Columns should be a list"
        assert len(cols) > 0, "Columns should not be empty"
        assert all("fieldname" in c and "label" in c for c in cols), "Each column should have fieldname and label"
        print(f"  ✓ get_columns() returns {len(cols)} columns")

        # Test with empty filters
        print("\nTesting report execution with empty filters...")
        filters = {}
        columns, data, message, chart, kpis = execute(filters)
        assert isinstance(columns, list), "Columns should be a list"
        assert isinstance(data, list), "Data should be a list"
        assert isinstance(kpis, list), "KPIs should be a list"
        assert isinstance(chart, dict), "Chart should be a dict"
        print(f"  ✓ execute() returns valid structure")
        print(f"    - Columns: {len(columns)}")
        print(f"    - Data rows: {len(data)}")
        print(f"    - KPIs: {len(kpis)}")

        # Test KPI structure
        assert len(kpis) == 12, f"Should have 12 KPIs, got {len(kpis)}"
        for kpi in kpis:
            assert "label" in kpi, "KPI should have label"
            assert "value" in kpi, "KPI should have value"
            assert "datatype" in kpi, "KPI should have datatype"
        print(f"  ✓ KPI structure valid (12 KPIs)")

        # Test chart structure
        assert "data" in chart, "Chart should have data"
        assert "labels" in chart["data"], "Chart data should have labels"
        assert "datasets" in chart["data"], "Chart data should have datasets"
        assert "type" in chart, "Chart should have type"
        print(f"  ✓ Chart structure valid (type: {chart.get('type')})")

        # Test dashboard data endpoint
        print("\nTesting get_dashboard_data()...")
        import json
        filters_json = json.dumps({})
        result = get_dashboard_data(filters_json)
        assert isinstance(result, dict), "Dashboard data should be a dict"
        assert "comparison" in result, "Should have comparison"
        assert "individual_performance" in result, "Should have individual_performance"
        assert "extra_charts" in result, "Should have extra_charts"
        print(f"  ✓ get_dashboard_data() structure valid")
        print(f"    - Comparison rows: {len(result['comparison']) if result['comparison'] else 0}")
        print(f"    - Extra charts: {len(result['extra_charts'])}")

        print("\n" + "="*50)
        print("✓ All integration tests passed!")
        print("="*50)
        return 0

    except Exception as e:
        print(f"\n✗ Test failed with error:")
        print(f"  {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(run_test())
