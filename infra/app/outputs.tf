output "instance_id" {
  value = aws_instance.main.id
}
output "public_ip" {
  value = aws_instance.main.public_ip
}
output "artifact_bucket" {
  value = aws_s3_bucket.artifacts.id
}
output "ami_id" {
  value = aws_instance.main.ami
}
