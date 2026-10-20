# Safety net for a free-tier demo: email if spend reaches $0.80 or $1 in a month.
# (The first two AWS Budgets in an account are free.)
resource "aws_budgets_budget" "guardrail" {
  count = var.budget_email == "" ? 0 : 1

  name         = "${var.project}-monthly-guardrail"
  budget_type  = "COST"
  limit_amount = "1"
  limit_unit   = "USD"
  time_unit    = "MONTHLY"

  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = 80
    threshold_type             = "PERCENTAGE"
    notification_type          = "ACTUAL"
    subscriber_email_addresses = [var.budget_email]
  }

  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = 100
    threshold_type             = "PERCENTAGE"
    notification_type          = "FORECASTED"
    subscriber_email_addresses = [var.budget_email]
  }
}
