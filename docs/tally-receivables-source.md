# Tally Receivables Source

For this product, the right Tally export is the invoice-level receivables or outstandings report, not a party-summary ageing report.

## Recommended Tally report

Use one of these Tally reports as the source:

- `Bills Receivable` or `Bills Outstanding` under `Gateway of Tally > Display More Reports > Statement of Accounts > Outstandings > Receivables`
- `Ledger Outstandings` when you want the detailed view for a single party ledger

Why this report:

- Tally documents it as the receivables view that shows `Pending Amount`, `Due on`, and `Overdue by days`
- the detailed form keeps invoice or bill references, which is what the copilot needs for partial payments, promises, and case timelines
- summary-only party reports collapse multiple invoices into one line and lose the operational trail

## Typical export shape

The sample file in this repo mirrors the columns most useful to the importer:

- `Date`
- `Ref No.`
- `Party's Name`
- `Opening Amount`
- `Pending Amount`
- `Due On`
- `Overdue by days`
- optional operator fields such as `Mobile`, `Sales Person`, `Remarks`, and `Party Code`

Real Tally exports often include spaces, punctuation, or apostrophes in the headers. The importer now recognizes those Tally-style headings directly.

## Repo sample

Use [sample_data/tally_bills_receivable_sample.csv](/sample_data/tally_bills_receivable_sample.csv) as a realistic starter file for local testing, demos, or manual imports.

## References

- [Manage Outstanding Receivables in TallyPrime](https://help.tallysolutions.com/manage-receivables-outstanding-tally/)
- [Ledger Outstandings Report](https://help.tallysolutions.com/docs/te9rel51/Reports/MIS_Reports/Ledger_Outstandings_Report.htm)
- [Pending Bills Receivables Summary](https://help.tallysolutions.com/docs/te9rel49/International_Audit/Pending_Bills_Receivables_Summary.htm)
