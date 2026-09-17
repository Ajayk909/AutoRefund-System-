output "identifier" {
  value = aws_db_instance.this.identifier
}

output "address" {
  value = aws_db_instance.this.address
}

output "port" {
  value = aws_db_instance.this.port
}

output "db_name" {
  value = aws_db_instance.this.db_name
}

output "master_username" {
  value = aws_db_instance.this.username
}

output "master_user_secret_arn" {
  description = "RDS-managed Secrets Manager secret holding the master password. ECS reads DB_PASSWORD from here."
  value       = aws_db_instance.this.master_user_secret[0].secret_arn
}

output "instance_arn" {
  value = aws_db_instance.this.arn
}
