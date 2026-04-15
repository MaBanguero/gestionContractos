provider "aws" {
  region = "us-east-1" # Cambia la región si prefieres otra
}

# 1. Grupo de Seguridad (Firewall)
resource "aws_security_group" "fastapi_sg" {
  name        = "fastapi_web_sg"
  description = "Permitir trafico HTTP y SSH"

  # Permitir SSH
  ingress {
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  # Permitir el puerto 8000 (Donde correrá FastAPI)
  ingress {
    from_port   = 8000
    to_port     = 8000
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  # Permitir salida a internet
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

# 2. Buscar la imagen (AMI) de Ubuntu 22.04 LTS más reciente
data "aws_ami" "ubuntu" {
  most_recent = true
  owners      = ["099720109477"] # Canonical

  filter {
    name   = "name"
    values = ["ubuntu/images/hvm-ssd/ubuntu-jammy-22.04-amd64-server-*"]
  }
}

# 3. Crear la Instancia EC2
resource "aws_instance" "app_server" {
  ami           = data.aws_ami.ubuntu.id
  instance_type = "t2.micro"

  vpc_security_group_ids = [aws_security_group.fastapi_sg.id]

  tags = {
    Name = "Servidor-Control-Financiero"
  }

  # 4. Script de Arranque
  user_data = <<-EOF
              #!/bin/bash
              apt-get update -y
              apt-get install -y python3-pip python3-venv git

              mkdir -p /opt/gestion_contratos
              cd /opt/gestion_contratos

              # RECUERDA CAMBIAR ESTA LÍNEA CON TU REPO
              git clone https://github.com/MaBanguero/gestionContractos.git .

              python3 -m venv venv
              source venv/bin/activate

              pip install -r requirements.txt
              pip install uvicorn

              cat << 'SERVICE' > /etc/systemd/system/fastapi.service
              [Unit]
              Description=FastAPI Aplicacion de Finanzas
              After=network.target

              [Service]
              User=root
              WorkingDirectory=/opt/gestion_contratos
              Environment="PATH=/opt/gestion_contratos/venv/bin"
              ExecStart=/opt/gestion_contratos/venv/bin/uvicorn main:app --host 0.0.0.0 --port 8000
              Restart=always

              [Install]
              WantedBy=multi-user.target
              SERVICE

              systemctl daemon-reload
              systemctl start fastapi
              systemctl enable fastapi
              EOF
}

# ==========================================
# LO NUEVO: 5. IP Elástica (IP Fija)
# ==========================================
resource "aws_eip" "app_eip" {
  instance = aws_instance.app_server.id
  domain   = "vpc"

  tags = {
    Name = "IP-Fija-Finanzas"
  }
}

# 6. Mostrar la nueva IP Pública Fija al terminar
output "ip_publica_servidor" {
  description = "Accede a tu aplicacion usando esta IP FIJA en el puerto 8000"
  value       = aws_eip.app_eip.public_ip
}