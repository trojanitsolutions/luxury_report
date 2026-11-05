# Copyright (c) 2026, Trojan IT Solutions and contributors
# For license information, please see license.txt

"""Integration tests for the POS Payment Invoice report.

The scenario invoices are real submitted POS Sales Invoices, so ERPNext computes
outstanding and rounded totals itself. The paging volume tests use raw rows
inserted with bulk_insert, because the report reads only the tables.
All data is rolled back at the end of the class.
"""

from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import flt

from luxury_report.luxury_report.report.pos_payment_invoice import export, queries
from luxury_report.luxury_report.report.pos_payment_invoice.pos_payment_invoice import (
	execute,
	get_page,
)

DATE = "2026-03-10"
BULK_DATE = "2026-02-10"
BULK_COUNT = 2600
PREFIX = "_PPI Test"


def _company():
	return frappe.db.get_value("Company", {}, "name", order_by="creation asc")


class TestPOSPaymentInvoice(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.company = _company()
		if not cls.company:
			raise RuntimeError("POS Payment Invoice tests need at least one Company on the site")

		frappe.set_user("Administrator")
		company = frappe.get_cached_doc("Company", cls.company)
		cls.cash_account = frappe.db.get_value(
			"Account", {"company": cls.company, "account_type": "Cash", "is_group": 0}, "name"
		)
		cls.cash = cls._mode_of_payment("Cash")
		cls.card = cls._mode_of_payment(f"{PREFIX} Card")
		cls.customer = cls._customer(f"{PREFIX} Customer")
		cls.other_customer = cls._customer(f"{PREFIX} Customer 2")
		cls.item_a = cls._item(f"{PREFIX} Item A")
		cls.item_b = cls._item(f"{PREFIX} Item B")
		cls.branch_a = cls._branch(f"{PREFIX} Branch A")
		cls.branch_b = cls._branch(f"{PREFIX} Branch B")
		cls.profile_a = cls._pos_profile(f"{PREFIX} Profile A", cls.branch_a, company)
		cls.profile_b = cls._pos_profile(f"{PREFIX} Profile B", cls.branch_b, company)
		cls.profile_bulk = cls._pos_profile(f"{PREFIX} Profile Bulk", cls.branch_b, company)

		cls.inv_cash = cls._invoice(cls.profile_a, [(cls.item_a, 1, 100)], [(cls.cash, 100)])
		cls.inv_card = cls._invoice(cls.profile_b, [(cls.item_a, 2, 50)], [(cls.card, 100)])
		cls.inv_multi_pay = cls._invoice(
			cls.profile_a, [(cls.item_a, 1, 100), (cls.item_b, 3, 50)], [(cls.cash, 150), (cls.card, 100)]
		)
		cls.inv_partly = cls._invoice(
			cls.profile_b, [(cls.item_b, 2, 100)], [(cls.cash, 50)], customer=cls.other_customer
		)
		cls.inv_unpaid = cls._invoice(cls.profile_a, [(cls.item_b, 1, 80)], [(cls.cash, 0)])
		cls.inv_return = cls._return(cls.inv_cash)
		cls.scenario = [
			cls.inv_cash,
			cls.inv_card,
			cls.inv_multi_pay,
			cls.inv_partly,
			cls.inv_unpaid,
			cls.inv_return,
		]
		cls._bulk_invoices()

	# ---------- fixtures ----------

	@classmethod
	def _mode_of_payment(cls, name):
		if not frappe.db.exists("Mode of Payment", name):
			frappe.get_doc({"doctype": "Mode of Payment", "mode_of_payment": name, "type": "Cash"}).insert()
		mop = frappe.get_doc("Mode of Payment", name)
		if not any(a.company == cls.company for a in mop.accounts):
			mop.append("accounts", {"company": cls.company, "default_account": cls.cash_account})
			mop.save()
		return name

	@classmethod
	def _customer(cls, name):
		if not frappe.db.exists("Customer", name):
			frappe.get_doc({"doctype": "Customer", "customer_name": name, "customer_type": "Individual"}).insert()
		return name

	@classmethod
	def _item(cls, name):
		if not frappe.db.exists("Item", name):
			frappe.get_doc(
				{
					"doctype": "Item",
					"item_code": name,
					"item_name": name,
					"item_group": frappe.db.get_value("Item Group", {"is_group": 0}, "name") or "All Item Groups",
					"stock_uom": "Nos",
					"is_stock_item": 0,
				}
			).insert()
		return name

	@classmethod
	def _branch(cls, name):
		if not frappe.db.exists("Branch", name):
			frappe.get_doc({"doctype": "Branch", "branch": name}).insert()
		return name

	@classmethod
	def _pos_profile(cls, name, branch, company):
		if not frappe.db.exists("POS Profile", name):
			frappe.get_doc(
				{
					"doctype": "POS Profile",
					"__newname": name,
					"name": name,
					"company": cls.company,
					"currency": company.default_currency,
					"warehouse": frappe.db.get_value(
						"Warehouse", {"company": cls.company, "is_group": 0}, "name"
					),
					"write_off_account": company.write_off_account or company.round_off_account,
					"write_off_cost_center": company.cost_center,
					"cost_center": company.cost_center,
					"selling_price_list": "Standard Selling",
					"update_stock": 0,
					"allow_partial_payment": 1,
					"payments": [{"mode_of_payment": cls.cash, "default": 1}, {"mode_of_payment": cls.card}],
				}
			).insert()
		# branch is fetched from warehouse.branch; set it directly for the test
		frappe.db.set_value("POS Profile", name, "branch", branch)
		return name

	@classmethod
	def _invoice(cls, pos_profile, items, payments, customer=None, posting_date=DATE):
		doc = frappe.get_doc(
			{
				"doctype": "Sales Invoice",
				"company": cls.company,
				"customer": customer or cls.customer,
				"is_pos": 1,
				"pos_profile": pos_profile,
				"set_posting_time": 1,
				"posting_date": posting_date,
				"due_date": posting_date,
				"update_stock": 0,
				"disable_rounded_total": 1,
				"items": [{"item_code": code, "qty": qty, "rate": rate} for code, qty, rate in items],
			}
		)
		doc.set_missing_values()
		doc.set("payments", [{"mode_of_payment": mop, "amount": amount} for mop, amount in payments])
		doc.insert()
		doc.submit()
		return doc.name

	@classmethod
	def _return(cls, against):
		from erpnext.controllers.sales_and_purchase_return import make_return_doc

		doc = make_return_doc("Sales Invoice", against)
		doc.update({"set_posting_time": 1, "posting_date": DATE, "due_date": DATE})
		doc.insert()
		doc.submit()
		return doc.name

	@classmethod
	def _bulk_invoices(cls):
		currency = frappe.get_cached_value("Company", cls.company, "default_currency")
		now = frappe.utils.now()
		fields = [
			"name", "creation", "modified", "owner", "modified_by", "docstatus", "company", "customer",
			"customer_name", "posting_date", "is_pos", "pos_profile", "currency", "grand_total",
			"rounded_total", "disable_rounded_total", "outstanding_amount",
		]  # fmt: skip
		values = [
			(
				f"{PREFIX}-BULK-{i:05d}", now, now, "Administrator", "Administrator", 1, cls.company,
				cls.customer, cls.customer, BULK_DATE, 1, cls.profile_bulk, currency, 10, 10, 1, 0,
			)  # fmt: skip
			for i in range(BULK_COUNT)
		]
		frappe.db.bulk_insert("Sales Invoice", fields, values)

	def setUp(self):
		frappe.db.savepoint("ppi_test")

	def tearDown(self):
		# undo changes a test makes to the class fixtures
		frappe.db.rollback(save_point="ppi_test")

	# ---------- helpers ----------

	def filters(self, **kwargs):
		base = {
			"company": self.company,
			"from_date": DATE,
			"to_date": DATE,
			"pos_profile": [self.profile_a, self.profile_b],
		}
		base.update(kwargs)
		return frappe._dict(base)

	def run_report(self, **kwargs):
		_columns, rows, _msg, _chart, summary = execute(self.filters(**kwargs))
		return rows, {card["label"]: card["value"] for card in summary}

	def invoice_rows(self, **kwargs):
		rows, _summary = self.run_report(**kwargs)
		return {row["name"]: row for row in rows if row["row_type"] == "invoice"}

	# ---------- payment methods and status ----------

	def test_cash_card_and_multiple_payment_methods(self):
		rows = self.invoice_rows()
		self.assertEqual(rows[self.inv_cash]["payment_method"], self.cash)
		self.assertEqual(rows[self.inv_card]["payment_method"], self.card)
		self.assertEqual(rows[self.inv_multi_pay]["payment_method"], f"{self.cash}, {self.card}")
		# zero-amount payment rows are not a payment method
		self.assertEqual(rows[self.inv_unpaid]["payment_method"], "")

	def test_payment_status_and_amounts(self):
		rows = self.invoice_rows()
		for name in (self.inv_cash, self.inv_card, self.inv_multi_pay):
			self.assertEqual(rows[name]["payment_status"], "Paid")
			self.assertEqual(flt(rows[name]["outstanding_amount"]), 0)
			self.assertEqual(flt(rows[name]["paid_amount"]), flt(rows[name]["grand_total"]))

		partly = rows[self.inv_partly]
		self.assertEqual(partly["payment_status"], "Partially Paid")
		self.assertEqual((flt(partly["paid_amount"]), flt(partly["outstanding_amount"])), (50, 150))

		unpaid = rows[self.inv_unpaid]
		self.assertEqual(unpaid["payment_status"], "Unpaid")
		self.assertEqual((flt(unpaid["paid_amount"]), flt(unpaid["outstanding_amount"])), (0, 80))

		self.assertEqual(rows[self.inv_return]["payment_status"], "Paid")
		self.assertLess(flt(rows[self.inv_return]["grand_total"]), 0)

	def test_branch_comes_from_pos_profile(self):
		rows = self.invoice_rows()
		self.assertEqual(rows[self.inv_cash]["branch"], self.branch_a)
		self.assertEqual(rows[self.inv_card]["branch"], self.branch_b)

	def test_only_submitted_pos_invoices(self):
		draft = frappe.copy_doc(frappe.get_doc("Sales Invoice", self.inv_cash))
		draft.docstatus = 0
		draft.insert()
		self.assertEqual(draft.docstatus, 0)
		non_pos = frappe.get_doc("Sales Invoice", self.inv_card)
		frappe.db.set_value("Sales Invoice", non_pos.name, "is_pos", 0)
		try:
			rows = self.invoice_rows()
			self.assertNotIn(draft.name, rows)
			self.assertNotIn(non_pos.name, rows)
		finally:
			frappe.db.set_value("Sales Invoice", non_pos.name, "is_pos", 1)

	# ---------- filters ----------

	def test_single_filters(self):
		self.assertEqual(set(self.invoice_rows(branch=self.branch_b)), {self.inv_card, self.inv_partly})
		self.assertEqual(
			set(self.invoice_rows(pos_profile=[self.profile_b])), {self.inv_card, self.inv_partly}
		)
		self.assertEqual(
			set(self.invoice_rows(mode_of_payment=[self.card])), {self.inv_card, self.inv_multi_pay}
		)
		self.assertEqual(set(self.invoice_rows(payment_status="Unpaid")), {self.inv_unpaid})
		self.assertEqual(set(self.invoice_rows(payment_status="Partially Paid")), {self.inv_partly})
		self.assertEqual(set(self.invoice_rows(customer=self.other_customer)), {self.inv_partly})
		self.assertEqual(set(self.invoice_rows(invoice=self.inv_card)), {self.inv_card})

	def test_combined_filters(self):
		rows = self.invoice_rows(branch=self.branch_a, mode_of_payment=[self.cash], payment_status="Paid")
		# the return refunds Cash too
		self.assertEqual(set(rows), {self.inv_cash, self.inv_multi_pay, self.inv_return})

	def test_channel_filter_guarded(self):
		rows = self.invoice_rows(channel=["Any Channel"])
		if queries.has_channel():
			self.assertEqual(rows, {})
		else:
			# no channel column on this site: the filter is ignored, the column is blank
			self.assertEqual(len(rows), len(self.scenario))
			self.assertTrue(all(row["channel"] is None for row in rows.values()))

	def test_date_range(self):
		self.assertEqual(self.invoice_rows(from_date="2026-03-11", to_date="2026-03-31"), {})
		self.assertEqual(len(self.invoice_rows(from_date="2026-03-01", to_date="2026-03-31")), len(self.scenario))
		with self.assertRaises(frappe.ValidationError):
			execute(self.filters(from_date="2026-03-31", to_date="2026-03-01"))

	def test_empty_result(self):
		rows, summary = self.run_report(customer=f"{PREFIX} No Such Customer")
		self.assertEqual(rows, [])
		self.assertEqual(summary["Invoices"], 0)

	# ---------- item details ----------

	def test_item_details_toggle(self):
		plain, _ = self.run_report()
		self.assertEqual(len(plain), len(self.scenario))
		self.assertTrue(all(row["row_type"] == "invoice" for row in plain))
		self.assertFalse(any("item_code" in row for row in plain))

		detailed, _ = self.run_report(show_item_details=1)
		invoices = [row for row in detailed if row["row_type"] == "invoice"]
		self.assertEqual(len(invoices), len(self.scenario))

		multi = [row for row in detailed if row["invoice"] == self.inv_multi_pay]
		self.assertEqual([row["row_type"] for row in multi], ["invoice", "item", "item"])
		self.assertEqual([row["item_code"] for row in multi[1:]], [self.item_a, self.item_b])
		self.assertEqual([flt(row["qty"]) for row in multi[1:]], [1, 3])
		# item rows carry no invoice amounts, so totals cannot double-count
		self.assertFalse(any(row.get("grand_total") for row in multi[1:]))

	def test_no_duplicate_invoice_rows(self):
		rows, _ = self.run_report(show_item_details=1, mode_of_payment=[self.cash, self.card])
		names = [row["name"] for row in rows if row["row_type"] == "invoice"]
		self.assertEqual(len(names), len(set(names)))

	def test_items_read_only_for_current_batch(self):
		with patch.object(queries, "get_items", wraps=queries.get_items) as get_items:
			execute(self.filters(show_item_details=1, page_size=50))
			execute(self.filters(show_item_details=0))
		get_items.assert_called_once()
		self.assertEqual(len(get_items.call_args.args[0]), len(self.scenario))

	def test_query_count_per_page(self):
		queries.has_channel(), queries.has_branch()  # warm the column cache
		with self.assertQueryCount(4, query_type=("select",)):
			execute(self.filters(show_item_details=1))
		with self.assertQueryCount(3, query_type=("select",)):
			get_page(self.filters(show_item_details=1), start=0)

	# ---------- paging ----------

	def bulk_filters(self, **kwargs):
		return self.filters(from_date=BULK_DATE, to_date=BULK_DATE, pos_profile=[self.profile_bulk], **kwargs)

	def test_page_sizes(self):
		for size in queries.PAGE_SIZES:
			_cols, rows, *_rest, summary = execute(self.bulk_filters(page_size=str(size)))
			self.assertEqual(len(rows), size)
			self.assertEqual(summary[0]["value"], BULK_COUNT)
		_cols, rows, *_ = execute(self.bulk_filters(page_size="37"))
		self.assertEqual(len(rows), 50)

	def test_load_more_batches_do_not_overlap(self):
		filters = self.bulk_filters(page_size="500")
		_cols, first, *_ = execute(filters)
		loaded = [row["name"] for row in first]
		while True:
			batch = get_page(frappe.as_json(filters), start=len(loaded))["rows"]
			if not batch:
				break
			self.assertEqual(batch[0]["sl_no"], len(loaded) + 1)
			loaded += [row["name"] for row in batch]
		self.assertEqual(len(loaded), BULK_COUNT)
		self.assertEqual(len(set(loaded)), BULK_COUNT)

	def test_load_more_keeps_filters(self):
		batch = get_page(frappe.as_json(self.filters(page_size="50", branch=self.branch_b)), start=1)["rows"]
		self.assertEqual(len(batch), 1)
		self.assertIn(batch[0]["name"], {self.inv_card, self.inv_partly})

	def test_totals_cover_all_matching_invoices(self):
		_rows, summary = self.run_report(page_size="50")
		expected = frappe.get_all(
			"Sales Invoice", filters={"name": ("in", self.scenario)}, fields=["grand_total", "outstanding_amount"]
		)
		self.assertEqual(summary["Invoices"], len(self.scenario))
		self.assertAlmostEqual(summary["Grand Total"], sum(flt(r.grand_total) for r in expected))
		self.assertAlmostEqual(summary["Outstanding Amount"], sum(flt(r.outstanding_amount) for r in expected))

	# ---------- export ----------

	def export_rows(self, filters, invoices=None):
		return list(export.iter_export_rows(filters, invoices))

	def test_export_selected_only(self):
		rows = self.export_rows(self.filters(), [self.inv_card, self.inv_partly])
		self.assertEqual({row["name"] for row in rows}, {self.inv_card, self.inv_partly})
		self.assertEqual([row["sl_no"] for row in rows], [1, 2])

	def test_export_selected_respects_filters(self):
		rows = self.export_rows(self.filters(branch=self.branch_a), [self.inv_card, self.inv_cash])
		self.assertEqual([row["name"] for row in rows], [self.inv_cash])

	def test_export_selected_with_items(self):
		rows = self.export_rows(self.filters(show_item_details=1), [self.inv_multi_pay])
		self.assertEqual([row["row_type"] for row in rows], ["invoice", "item", "item"])

	def test_export_all_filtered_in_chunks(self):
		with patch.object(export, "CHUNK_SIZE", 700):
			rows = self.export_rows(self.bulk_filters(page_size="50"))
		self.assertEqual(len(rows), BULK_COUNT)
		self.assertEqual(len({row["name"] for row in rows}), BULK_COUNT)
		self.assertEqual(rows[-1]["sl_no"], BULK_COUNT)

	def test_export_file_formats(self):
		filters = frappe.as_json(self.filters(show_item_details=1))
		export.export_report(filters, frappe.as_json([self.inv_multi_pay]), "Excel")
		self.assertEqual(frappe.response["type"], "binary")
		self.assertTrue(frappe.response["filecontent"].startswith(b"PK"))

		export.export_report(filters, "[]", "CSV")
		self.assertEqual(frappe.response["type"], "csv")
		lines = frappe.response["result"].strip().splitlines()
		# header + scenario invoices + their items + total row
		items = frappe.db.count("Sales Invoice Item", {"parent": ("in", self.scenario)})
		self.assertEqual(len(lines), 1 + len(self.scenario) + items + 1)
