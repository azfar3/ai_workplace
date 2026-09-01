"""
Seed WhatsApp test data for employee EMP-MM-00809 (Muhammad Arfan).

Run:
    bench --site erp.v15 execute ai_workplace.scripts.seed_whatsapp_test_employee.seed
"""

from __future__ import annotations

import calendar
from datetime import date

import frappe
from frappe.utils import add_days, add_months, flt, get_first_day, get_last_day, getdate, today

EMPLOYEE_ID = "EMP-MM-00809"
SUPERVISOR_ID = "EMP-MM-00786"
TEST_USER_EMAIL = "muhammad.arfan@micromerger.com"
LEAVE_PERIOD = "HR-LPR-2026-00001"
COMPANY = "MicroMerger (Pvt.) Ltd."
BULK_TAG = "[WA-TEST]"
LEAVE_POLICY = "HR-LPOL-2025-00001"
HOLIDAY_LIST = "2025-26"
DEFAULT_SHIFT = "Morning"
RECORDS_PER_MONTH = 12  # 10-20 range; 12 x 2 months per section
SALARY_SLIP_MONTHS = 8  # submitted slips for WhatsApp payroll download tests

LEAVE_TYPES = ("Casual Leave", "Sick Leave", "Annual Leaves")
ATT_REQUEST_REASONS = ("Check In Miss", "Check Out Miss", "On Duty", "On Duty", "Check In Miss")
TRAVEL_DESTINATIONS = ("Islamabad", "Quetta", "Islamabad", "Other", "Islamabad")
EXPENSE_MONTHS = ("July", "August")


def seed():
	frappe.set_user("Administrator")
	results: list[str] = []

	for fn in (
		_ensure_user_and_whatsapp_link,
		_update_employee_profile,
		_assign_hr_settings,
		_seed_leave_allocations,
		_seed_bulk_attendance,
		_seed_bulk_leave_applications,
		_seed_bulk_attendance_requests,
		_seed_bulk_travel_requests,
		_seed_bulk_expense_claims,
		_seed_bulk_salary_slips,
	):
		try:
			results.append(fn())
			frappe.db.commit()
		except Exception as exc:
			frappe.db.rollback()
			results.append(f"{fn.__name__} FAILED: {exc}")
			frappe.log_error(title=f"WhatsApp seed failed: {fn.__name__}", message=frappe.get_traceback())

	print("\n".join(r for r in results if r))
	print("\nSeed completed for", EMPLOYEE_ID)


def _month_ranges() -> list[tuple[date, date, str]]:
	"""Current month and previous month (weekday-only seed window)."""
	curr = getdate(today())
	prev = getdate(add_months(curr, -1))
	ranges = []
	for d in (prev, curr):
		start = getdate(get_first_day(d))
		end = getdate(get_last_day(d))
		if d.month == curr.month:
			end = min(end, curr)
		ranges.append((start, end, d.strftime("%B %Y")))
	return ranges


def _weekdays(start: date, end: date) -> list[date]:
	out = []
	day = start
	while day <= end:
		if day.weekday() < 5:
			out.append(day)
		day = add_days(day, 1)
	return out


def _approver() -> str:
	return frappe.db.get_value("Employee", EMPLOYEE_ID, "leave_approver") or "trainingtest@gmail.com"


def _employee_name() -> str:
	return frappe.db.get_value("Employee", EMPLOYEE_ID, "employee_name") or "Muhammad Arfan"


def _set_workflow(doctype: str, name: str, state: str) -> None:
	frappe.db.sql(f"UPDATE `tab{doctype}` SET workflow_state=%s WHERE name=%s", (state, name))


def _bulk_count(doctype: str, text_field: str, month_label: str) -> int:
	return frappe.db.count(
		doctype,
		{
			"employee": EMPLOYEE_ID,
			text_field: ["like", f"%{BULK_TAG} {month_label}%"],
			"docstatus": ["!=", 2],
		},
	)


def _update_employee_profile() -> str:
	emp = frappe.get_doc("Employee", EMPLOYEE_ID)
	supervisor = frappe.get_doc("Employee", SUPERVISOR_ID)
	approver_email = supervisor.user_id or supervisor.prefered_email or "trainingtest@gmail.com"

	emp.department = emp.department or "Management"
	emp.reports_to = SUPERVISOR_ID
	emp.leave_approver = approver_email
	emp.expense_approver = approver_email
	emp.employment_type = emp.employment_type or "Full-time"
	emp.company_email = TEST_USER_EMAIL
	emp.personal_email = emp.personal_email or "arfan.personal@gmail.com"
	emp.cnic = emp.cnic or "61101-1234567-1"
	emp.bank_name = emp.bank_name or "Habib Bank Limited"
	emp.bank_ac_no = emp.bank_ac_no or "01010102938475"
	emp.bank_account_title = emp.bank_account_title or emp.employee_name
	emp.person_to_be_contacted = emp.person_to_be_contacted or "Fatima Arfan (Wife)"
	emp.emergency_phone_number = emp.emergency_phone_number or "03001234567"
	emp.direct_supervisor_name = supervisor.employee_name
	emp.direct_supervisor_email = approver_email
	emp.expense_claim_structure = emp.expense_claim_structure or "ComNet"
	emp.attendance_device_id = emp.attendance_device_id or "WA-BIO-00809"
	emp.save(ignore_permissions=True)
	_ensure_expense_claim_structure_assignment()
	return "Employee profile updated."


def _assign_hr_settings() -> str:
	frappe.db.set_value(
		"Employee",
		EMPLOYEE_ID,
		{
			"leave_policy": LEAVE_POLICY,
			"holiday_list": HOLIDAY_LIST,
			"default_shift": DEFAULT_SHIFT,
		},
	)
	return f"HR settings: leave_policy={LEAVE_POLICY}, holiday_list={HOLIDAY_LIST}, shift={DEFAULT_SHIFT}."


def _ensure_user_and_whatsapp_link() -> str:
	if frappe.db.get_value("Employee", EMPLOYEE_ID, "user_id") == TEST_USER_EMAIL and not frappe.db.exists(
		"User", TEST_USER_EMAIL
	):
		frappe.db.set_value("Employee", EMPLOYEE_ID, "user_id", None)

	if not frappe.db.exists("User", TEST_USER_EMAIL):
		user = frappe.get_doc(
			{
				"doctype": "User",
				"email": TEST_USER_EMAIL,
				"first_name": "Muhammad",
				"last_name": "Arfan",
				"send_welcome_email": 0,
				"user_type": "System User",
			}
		)
		user.append("roles", {"role": "Employee"})
		user.insert(ignore_permissions=True)

	frappe.db.set_value("Employee", EMPLOYEE_ID, "user_id", TEST_USER_EMAIL)
	wa_name = frappe.db.get_value("WhatsApp Identity", {"employee": EMPLOYEE_ID}, "name")
	if wa_name:
		frappe.db.set_value("WhatsApp Identity", wa_name, "erp_user", TEST_USER_EMAIL)
	return f"ERP User linked: {TEST_USER_EMAIL}"


def _ensure_expense_claim_structure_assignment() -> None:
	name = frappe.db.get_value(
		"Expense Claim Structure Assigment",
		{"employee": EMPLOYEE_ID, "docstatus": ["!=", 2]},
		"name",
	)
	if name:
		frappe.db.set_value("Expense Claim Structure Assigment", name, "travel_days", 60)
		return

	frappe.get_doc(
		{
			"doctype": "Expense Claim Structure Assigment",
			"employee": EMPLOYEE_ID,
			"expense_claim_structure": "ComNet",
			"company": COMPANY,
			"from_date": today(),
			"dsa_per_month": 15000,
			"total_dsa_allowed": 50000,
			"travel_days": 60,
			"travel_per_month": 10000,
			"total_travel": 100000,
		}
	).insert(ignore_permissions=True)


def _seed_leave_allocations() -> str:
	created = []
	leave_types = [("Casual Leave", 20, 14), ("Sick Leave", 12, 9), ("Annual Leaves", 18, 12)]
	from_date, to_date = frappe.db.get_value("Leave Period", LEAVE_PERIOD, ["from_date", "to_date"])

	for leave_type, total, unused in leave_types:
		existing = frappe.db.get_value(
			"Leave Allocation",
			{
				"employee": EMPLOYEE_ID,
				"leave_type": leave_type,
				"from_date": from_date,
				"to_date": to_date,
				"docstatus": ["!=", 2],
			},
			"name",
		)
		if existing:
			frappe.db.set_value(
				"Leave Allocation",
				existing,
				{"total_leaves_allocated": total, "unused_leaves": unused, "new_leaves_allocated": total},
			)
			continue

		doc = frappe.get_doc(
			{
				"doctype": "Leave Allocation",
				"employee": EMPLOYEE_ID,
				"leave_type": leave_type,
				"from_date": from_date,
				"to_date": to_date,
				"leave_period": LEAVE_PERIOD,
				"company": COMPANY,
				"new_leaves_allocated": total,
				"unused_leaves": unused,
				"total_leaves_allocated": total,
			}
		)
		doc.insert(ignore_permissions=True)
		doc.submit()
		created.append(leave_type)

	return f"Leave allocations: {', '.join(created) or 'updated/exist'}."


def _seed_bulk_attendance() -> str:
	created = 0
	curr = getdate(today())
	status_cycle = ["Present", "Present", "Present", "Absent", "Present", "Present"]

	for start, end, month_label in _month_ranges():
		existing = _bulk_count("Attendance", "custom_remarks", month_label) if frappe.db.has_column(
			"Attendance", "custom_remarks"
		) else frappe.db.count(
			"Attendance",
			{"employee": EMPLOYEE_ID, "attendance_date": ["between", [start, end]], "docstatus": ["!=", 2]},
		)
		if existing >= RECORDS_PER_MONTH:
			continue

		days = _weekdays(start, end)
		step = max(1, len(days) // RECORDS_PER_MONTH)
		picked = days[::step][:RECORDS_PER_MONTH]

		for idx, day in enumerate(picked):
			if frappe.db.exists(
				"Attendance",
				{"employee": EMPLOYEE_ID, "attendance_date": day, "docstatus": ["!=", 2]},
			):
				continue

			status = status_cycle[idx % len(status_cycle)]
			att = frappe.get_doc(
				{
					"doctype": "Attendance",
					"employee": EMPLOYEE_ID,
					"employee_name": _employee_name(),
					"attendance_date": day,
					"company": COMPANY,
					"status": status,
					"working_hours": 0 if status == "Absent" else 8.0,
					"late_entry": 1 if idx % 4 == 0 and status == "Present" else 0,
				}
			)
			if status == "Present":
				att.in_time = f"{day} 09:15:00"
				att.out_time = f"{day} 18:05:00"
				att.working_hours = 8.5

			att.insert(ignore_permissions=True)
			att.submit()
			created += 1

	# Today check-ins for WhatsApp "today" view
	if not frappe.db.exists(
		"Attendance",
		{"employee": EMPLOYEE_ID, "attendance_date": curr, "docstatus": ["!=", 2]},
	):
		today_att = frappe.get_doc(
			{
				"doctype": "Attendance",
				"employee": EMPLOYEE_ID,
				"employee_name": _employee_name(),
				"attendance_date": curr,
				"company": COMPANY,
				"status": "Present",
				"in_time": f"{curr} 09:15:00",
				"out_time": f"{curr} 18:05:00",
				"working_hours": 8.5,
				"late_entry": 1,
			}
		)
		today_att.insert(ignore_permissions=True)
		today_att.submit()
		created += 1

	for log_type, hour in (("IN", 9), ("OUT", 18)):
		ts = f"{curr} {hour:02d}:15:00"
		if not frappe.db.exists("Employee Checkin", {"employee": EMPLOYEE_ID, "time": ts}):
			frappe.get_doc(
				{
					"doctype": "Employee Checkin",
					"employee": EMPLOYEE_ID,
					"time": ts,
					"date": curr,
					"log_type": log_type,
					"device_id": "WhatsApp-Test-Seed",
				}
			).insert(ignore_permissions=True)

	return f"Attendance: {created} new records (Jul + Aug weekdays)."


def _fix_leave_application_series() -> None:
	"""Sync stale naming-series counter (site has HR-LAP-2026-000xx and HR-LAP-2026-038xx)."""
	max_num = frappe.db.sql(
		"""
		SELECT MAX(CAST(SUBSTRING_INDEX(name, '-', -1) AS UNSIGNED))
		FROM `tabLeave Application`
		WHERE name LIKE 'HR-LAP-2026-%%'
		"""
	)[0][0] or 0
	current = frappe.db.sql(
		"SELECT `current` FROM tabSeries WHERE name='HR-LAP-2026-'"
	)
	current = int(current[0][0]) if current else 0
	if int(max_num) >= current:
		if current:
			frappe.db.sql(
				"UPDATE tabSeries SET `current`=%s WHERE name='HR-LAP-2026-'",
				(int(max_num) + 1,),
			)
		else:
			frappe.db.sql(
				"INSERT INTO tabSeries (name, `current`) VALUES ('HR-LAP-2026-', %s)",
				(int(max_num) + 1,),
			)


def _seed_bulk_leave_applications() -> str:
	created = 0
	status_cycle = ["Open", "Approved", "Rejected", "Open", "Approved", "Rejected"]
	curr = getdate(today())
	_fix_leave_application_series()

	for start, end, month_label in _month_ranges():
		if _bulk_count("Leave Application", "description", month_label) >= RECORDS_PER_MONTH:
			continue

		for idx in range(RECORDS_PER_MONTH):
			status = status_cycle[idx % len(status_cycle)]
			leave_type = LEAVE_TYPES[idx % len(LEAVE_TYPES)]
			marker = f"{BULK_TAG} {month_label} #{idx + 1}"

			if frappe.db.exists(
				"Leave Application",
				{"employee": EMPLOYEE_ID, "description": ["like", f"{marker}%"], "docstatus": ["!=", 2]},
			):
				continue

			# Use future dates to avoid attendance conflicts; stagger by month
			base = 10 if "July" in month_label else 40
			from_d = add_days(curr, base + (idx * 2))
			to_d = from_d if idx % 3 else add_days(from_d, 1)

			doc = frappe.get_doc(
				{
					"doctype": "Leave Application",
					"employee": EMPLOYEE_ID,
					"leave_type": leave_type,
					"from_date": from_d,
					"to_date": to_d,
					"company": COMPANY,
					"description": f"{marker} — {status.lower()} {leave_type}",
					"status": "Open" if status == "Open" else status,
					"leave_approver": _approver(),
				}
			)
			try:
				doc.insert(ignore_permissions=True)
				if status in ("Approved", "Rejected"):
					frappe.db.set_value("Leave Application", doc.name, "status", status)
				frappe.db.commit()
				created += 1
			except frappe.DuplicateEntryError:
				frappe.db.rollback()
				continue

	return f"Leave applications: {created} new (Open / Approved / Rejected)."


def _seed_bulk_attendance_requests() -> str:
	created = 0
	wf_cycle = ["Pending", "Approved", "Rejected", "Pending", "Approved", "Rejected"]
	curr = getdate(today())

	for start, end, month_label in _month_ranges():
		if _bulk_count("Attendance Request", "explanation", month_label) >= RECORDS_PER_MONTH:
			continue

		days = [d for d in _weekdays(start, end) if d < curr]
		if not days:
			continue
		step = max(1, len(days) // RECORDS_PER_MONTH)
		picked = days[::step][:RECORDS_PER_MONTH]

		for idx, day in enumerate(picked):
			reason = ATT_REQUEST_REASONS[idx % len(ATT_REQUEST_REASONS)]
			wf = wf_cycle[idx % len(wf_cycle)]
			marker = f"{BULK_TAG} {month_label} #{idx + 1}"

			if frappe.db.exists(
				"Attendance Request",
				{"employee": EMPLOYEE_ID, "explanation": ["like", f"{marker}%"], "docstatus": ["!=", 2]},
			):
				continue

			payload = {
				"doctype": "Attendance Request",
				"employee": EMPLOYEE_ID,
				"company": COMPANY,
				"from_date": day,
				"to_date": day,
				"reason": reason,
				"explanation": f"{marker} — {wf.lower()} {reason}",
				"leave_approver": _approver(),
			}
			if reason == "On Duty":
				payload["from_time"] = "09:00:00"
				payload["to_time"] = "18:00:00"

			doc = frappe.get_doc(payload)
			doc.insert(ignore_permissions=True)
			if wf != "Pending":
				_set_workflow("Attendance Request", doc.name, wf)
			created += 1

	return f"Attendance requests: {created} new (Pending / Approved / Rejected)."


def _seed_bulk_travel_requests() -> str:
	created = 0
	wf_cycle = ["Pending", "Approved", "Rejected", "Pending", "Approved", "Rejected"]
	curr = getdate(today())

	for month_idx, (start, end, month_label) in enumerate(_month_ranges()):
		if _bulk_count("Travel Authorisation Request Form", "purpose_of_travel", month_label) >= RECORDS_PER_MONTH:
			continue

		for idx in range(RECORDS_PER_MONTH):
			wf = wf_cycle[idx % len(wf_cycle)]
			dest = TRAVEL_DESTINATIONS[idx % len(TRAVEL_DESTINATIONS)]
			marker = f"{BULK_TAG} {month_label} #{idx + 1}"

			if frappe.db.exists(
				"Travel Authorisation Request Form",
				{"employee": EMPLOYEE_ID, "purpose_of_travel": ["like", f"{marker}%"], "docstatus": ["!=", 2]},
			):
				continue

			# Stagger dates to avoid overlap: Jul backdated, Aug+ future windows
			if month_idx == 0:
				from_d = add_days(start, 1 + (idx * 2))
				to_d = add_days(from_d, 1)
			else:
				from_d = add_days(curr, 35 + (idx * 4))
				to_d = add_days(from_d, 1)

			doc = frappe.get_doc(
				{
					"doctype": "Travel Authorisation Request Form",
					"employee": EMPLOYEE_ID,
					"posting_date": from_d,
					"purpose_of_travel": f"{marker} — {wf.lower()} travel to {dest}",
					"project": "ComNet - HR",
					"travel_information": [
						{
							"from_date": from_d,
							"to_date": to_d,
							"source": "Karachi",
							"destination": dest,
							"mode_of_travel": "By Air",
							"description": f"WhatsApp test travel {month_label}",
							"night_stay": 1,
							"hotel_accommodation_required": "Yes",
						}
					],
				}
			)
			if getdate(from_d) < curr:
				doc.flags.ignore_validate = True
			try:
				doc.insert(ignore_permissions=True)
			except frappe.ValidationError as exc:
				if "Overlap" in str(exc):
					continue
				raise
			if wf != "Pending":
				_set_workflow("Travel Authorisation Request Form", doc.name, wf)
			created += 1

	return f"Travel authorisation: {created} new (Pending / Approved / Rejected)."


def _seed_bulk_expense_claims() -> str:
	created = 0
	wf_cycle = ["Draft", "Approved", "Rejected by Supervisor", "Draft", "Approved", "Rejected by HR"]
	curr = getdate(today())

	for month_idx, (start, end, month_label) in enumerate(_month_ranges()):
		if _bulk_count("Employee Expense Claim", "purpose_of_travel", month_label) >= RECORDS_PER_MONTH:
			continue

		month_name = start.strftime("%B")
		year_str = str(start.year)

		for idx in range(RECORDS_PER_MONTH):
			wf = wf_cycle[idx % len(wf_cycle)]
			marker = f"{BULK_TAG} {month_label} #{idx + 1}"

			if frappe.db.exists(
				"Employee Expense Claim",
				{"employee": EMPLOYEE_ID, "purpose_of_travel": ["like", f"{marker}%"], "docstatus": ["!=", 2]},
			):
				continue

			travel_day = add_days(start, 1 + idx)
			doc = frappe.get_doc(
				{
					"doctype": "Employee Expense Claim",
					"employee": EMPLOYEE_ID,
					"purpose_of_travel": f"{marker} — {wf.lower()} expense claim",
					"mode_of_travel": "By Air",
					"posting_date": travel_day,
					"year": year_str,
					"month": month_name,
					"travel_assigment_district": "Islamabad",
					"travel_information": [
						{
							"travel_date": travel_day,
							"source": "Karachi",
							"destination": "Islamabad",
							"from_time": "09:00:00",
							"to_time": "18:00:00",
						}
					],
					"other_expenses": [
						{"type": "Meals", "amount": 2000 + (idx * 100), "detail": f"Meals {month_label}"},
						{"type": "Local Conveyance", "amount": 800 + (idx * 50), "detail": "Taxi"},
					],
				}
			)
			doc.insert(ignore_permissions=True)
			if wf != "Draft":
				_set_workflow("Employee Expense Claim", doc.name, wf)
			created += 1

	return f"Expense claims: {created} new (Draft / Approved / Rejected)."


def _salary_slip_month_starts() -> list[date]:
	"""Last N complete calendar months before the current month."""
	curr = getdate(today())
	starts: list[date] = []
	for offset in range(1, SALARY_SLIP_MONTHS + 1):
		month_ref = add_months(curr, -offset)
		starts.append(getdate(get_first_day(month_ref)))
	return sorted(starts)


def _salary_structure_for_date(period_start: date) -> str | None:
	rows = frappe.get_all(
		"Salary Structure Assignment",
		filters={"employee": EMPLOYEE_ID, "docstatus": 1, "from_date": ["<=", period_start]},
		fields=["salary_structure"],
		order_by="from_date desc",
		limit=1,
	)
	return rows[0]["salary_structure"] if rows else None


def _seed_bulk_salary_slips() -> str:
	"""Create submitted salary slips for the last 8 months (ERP default print format)."""
	from erpnext.accounts.utils import get_fiscal_year
	from hrms.payroll.doctype.salary_structure.salary_structure import make_salary_slip

	created = 0
	submitted_drafts = 0
	skipped = 0
	failed: list[str] = []

	for period_start in _salary_slip_month_starts():
		period_end = get_last_day(period_start)
		posting_date = add_days(period_end, -3)
		month_name = period_start.strftime("%B")

		existing = frappe.db.get_value(
			"Salary Slip",
			{
				"employee": EMPLOYEE_ID,
				"start_date": period_start,
				"end_date": period_end,
				"docstatus": ["!=", 2],
			},
			["name", "docstatus"],
			as_dict=True,
		)
		if existing:
			if existing.docstatus == 0:
				doc = frappe.get_doc("Salary Slip", existing.name)
				doc.submit()
				submitted_drafts += 1
			else:
				skipped += 1
			continue

		structure = _salary_structure_for_date(period_start)
		if not structure:
			failed.append(f"{month_name} (no salary structure)")
			continue

		fiscal_year = get_fiscal_year(posting_date)[0]
		slip = frappe.get_doc(
			{
				"doctype": "Salary Slip",
				"employee": EMPLOYEE_ID,
				"employee_name": _employee_name(),
				"salary_structure": structure,
				"company": COMPANY,
				"posting_date": posting_date,
				"start_date": period_start,
				"end_date": period_end,
				"custom_payment_start_date": period_start,
				"custom_payment_end_date": period_end,
				"month": month_name,
				"fiscal_year": fiscal_year,
			}
		)

		try:
			doc = make_salary_slip(structure, slip, EMPLOYEE_ID, posting_date=posting_date)
			doc.month = month_name
			doc.fiscal_year = fiscal_year
			doc.custom_payment_start_date = period_start
			doc.custom_payment_end_date = period_end
			doc.insert(ignore_permissions=True)
			frappe.db.commit()
			doc.reload()
			doc.submit()
			frappe.db.commit()
			created += 1
		except frappe.ValidationError as exc:
			frappe.db.rollback()
			if "already created" in str(exc):
				skipped += 1
				continue
			failed.append(f"{month_name} ({exc})")
		except Exception as exc:
			frappe.db.rollback()
			failed.append(f"{month_name} ({exc})")
			frappe.log_error(
				title=f"WhatsApp seed salary slip failed: {month_name}",
				message=frappe.get_traceback(),
			)

	parts = [f"Salary slips: {created} new"]
	if submitted_drafts:
		parts.append(f"{submitted_drafts} drafts submitted")
	if skipped:
		parts.append(f"{skipped} already existed")
	if failed:
		parts.append(f"failed: {', '.join(failed)}")
	return ", ".join(parts) + "."
