ALL = ["employee", "manager", "hr", "exec"]
MGR = ["manager", "hr", "exec"]
HR = ["hr", "exec"]
EXEC = ["exec"]


def _d(slug, title, classification, roles, content):
    return {"slug": slug, "title": title, "classification": classification,
            "allowed_roles": roles, "content": content}


DOCS = [
    _d("pto-policy", "Paid Time Off Policy", "public", ALL,
       "Nimbus Corp employees receive 18 days of paid time off per year, plus one extra day per completed year of service up to a maximum of 25 days. Up to 5 unused days carry over into the next calendar year. PTO requests of more than 5 consecutive days need manager approval at least 14 days ahead."),
    _d("remote-work", "Remote Work Guidelines", "public", ALL,
       "Nimbus Corp runs a hybrid model: 3 days per week in the office, 2 remote. Core collaboration hours are 10:00 to 16:00 Singapore time. Working from another country is limited to 20 days per year and needs HR approval for tax reasons."),
    _d("benefits-overview", "Benefits Overview", "public", ALL,
       "Health insurance premiums are covered 90 percent by Nimbus Corp for employees and 50 percent for dependants. Every employee gets an annual wellness stipend of 1,200 dollars and a learning budget of 2,000 dollars per year."),
    _d("expense-policy", "Travel and Expense Policy", "internal", ALL,
       "Meals while travelling are reimbursed up to 60 dollars per day. Flights longer than 6 hours may be booked in premium economy. All expenses must be submitted within 30 days with receipts."),
    _d("code-of-conduct", "Code of Conduct", "public", ALL,
       "All Nimbus Corp staff are expected to treat colleagues with respect and to report harassment or discrimination to HR or the anonymous ethics hotline. Retaliation against anyone who reports in good faith is grounds for dismissal."),
    _d("holiday-calendar-2026", "2026 Holiday Calendar", "public", ALL,
       "Company holidays in 2026 include New Year's Day, Chinese New Year (two days), Good Friday, Labour Day, Hari Raya Puasa, Vesak Day, National Day on 9 August, Deepavali and Christmas Day. The office is closed between Christmas and New Year."),
    _d("salary-bands", "Salary Bands L3 to L5", "confidential", MGR,
       "Annual base salary bands: L3 from 78,000 to 98,000 dollars, L4 from 98,000 to 125,000 dollars, L5 from 125,000 to 160,000 dollars. Managers may propose offers within the band; anything above the band midpoint needs HR approval."),
    _d("performance-review-guide", "Performance Review Guide", "internal", MGR,
       "Reviews run twice a year with calibration sessions in June and December. Ratings are 1 to 5, and no more than 15 percent of a team may be rated 5. Managers must share written feedback with each report at least 5 days before the review meeting."),
    _d("promotion-criteria", "Promotion Criteria", "internal", MGR,
       "Promotion to L5 requires two consecutive ratings of 4 or above, demonstrated technical leadership across at least two teams, and sponsor endorsement from a director. Promotion cycles close on 15 May and 15 November."),
    _d("headcount-plan-q4", "Q4 Headcount Plan", "confidential", MGR,
       "Approved Q4 hiring: Engineering plus 6 heads, Customer Support plus 2 heads, Sales plus 3 heads. Hiring in Marketing is frozen until January. Backfills for resignations are exempt from the freeze."),
    _d("attrition-report", "Team Attrition Report", "confidential", MGR,
       "Company-wide attrition over the last 12 months is 11.4 percent, of which regretted attrition is 4.1 percent. Engineering attrition is highest at 14.2 percent, mainly to competitors offering larger equity grants."),
    _d("case-4172", "HR Case 4172: Grievance filed by Alex Tan", "restricted", HR,
       "Alex Tan (alex.tan@nimbus-corp.example, mobile +65 9123 4567, NRIC S1234567D) filed a grievance on 12 August about unequal overtime allocation in the Platform team. Investigation is led by Priya Nair with Daniel Ong interviewed as the line manager. Outcome pending."),
    _d("case-4188", "HR Case 4188: Disciplinary review of Wei Jie Koh", "restricted", HR,
       "Wei Jie Koh (wj.koh@nimbus-corp.example, mobile +65 8222 0199) received a written warning on 3 September for repeated unapproved access to the payroll system. A final warning follows any second breach within 12 months."),
    _d("comp-adjustments-2026", "2026 Compensation Adjustments", "restricted", HR,
       "Approved mid-year adjustments: Alex Tan from 118,000 to 127,500 dollars, Maya Lim from 104,000 to 111,000 dollars, Wei Jie Koh unchanged pending the disciplinary outcome. Total uplift is 2.3 percent of the Engineering payroll."),
    _d("termination-checklist", "Termination and Offboarding Checklist", "restricted", HR,
       "On termination HR must disable accounts within 1 hour, collect equipment within 3 working days, and confirm final pay including accrued PTO within 7 days. Severance beyond statutory minimum needs Chief People Officer sign-off."),
    _d("background-check-vendor", "Background Check Vendor Contract", "confidential", HR,
       "Nimbus Corp uses Verity Screens for pre-employment checks at 85 dollars per candidate. Reports are retained for 12 months and may only be viewed by HR Business Partners and the Chief People Officer."),
    _d("project-aurora", "Project Aurora: Platform and Data Reorganisation", "restricted", EXEC,
       "Project Aurora merges the Platform and Data organisations effective 5 January 2027. About 40 roles are affected and the severance budget is 2.1 million dollars. The announcement is embargoed until the board meeting on 20 November."),
    _d("lumen-acquisition", "Acquisition Memo: Lumen Analytics", "restricted", EXEC,
       "The board approved acquiring Lumen Analytics for 48 million dollars, with signing planned for 14 November. Retention packages are budgeted for 12 key Lumen engineers. Public announcement is not permitted before signing."),
    _d("exec-compensation", "Executive Compensation Review", "restricted", EXEC,
       "Executive base salaries were benchmarked at the 60th percentile. The Chief Executive's target bonus is 80 percent of base, and the Chief People Officer's is 50 percent. Long-term incentive grants vest over four years with a one-year cliff."),
    _d("layoff-contingency", "Layoff Contingency Plan", "restricted", EXEC,
       "If revenue falls more than 12 percent below plan for two consecutive quarters, the contingency plan reduces headcount by up to 8 percent, starting with non-customer-facing roles. Notice periods follow local law and a 3-month minimum is offered."),
]
