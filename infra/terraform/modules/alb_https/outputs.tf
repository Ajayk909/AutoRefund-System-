output "alb_dns_name" {
  value = aws_lb.this.dns_name
}

output "alb_arn_suffix" {
  value = aws_lb.this.arn_suffix
}

output "target_group_arn" {
  value = aws_lb_target_group.core_api.arn
}

output "target_group_arn_suffix" {
  value = aws_lb_target_group.core_api.arn_suffix
}

output "acm_certificate_arn" {
  value = aws_acm_certificate.this.arn
}

output "acm_validation_record_fqdn" {
  description = "Full CNAME name ACM wants. Strip the trailing \".<your-domain>.\" to get the Namecheap Host field."
  value       = local.validation_option.resource_record_name
}

output "acm_validation_record_value" {
  value = local.validation_option.resource_record_value
}

output "acm_validation_record_type" {
  value = local.validation_option.resource_record_type
}
