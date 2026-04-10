from sqlalchemy import Column, String, Integer, Float, ForeignKey, DateTime, Text
from sqlalchemy.orm import relationship
from datetime import datetime
from core.database import Base


class DBContratista(Base):
    __tablename__ = "contratistas"
    identificacion = Column(String, primary_key=True, index=True)
    nombre = Column(String, nullable=False)
    expedida_en = Column(String, nullable=True)
    telefono = Column(String, nullable=True)
    direccion = Column(String, nullable=True)
    tipo_persona = Column(String, nullable=True)
    contratos = relationship("DBContrato", back_populates="contratista")


class DBContrato(Base):
    __tablename__ = "contratos"
    numero_contrato = Column(String, primary_key=True, index=True)
    contratista_id = Column(String, ForeignKey("contratistas.identificacion"))
    valor_total = Column(Float, nullable=False)
    fecha_inicio = Column(String, nullable=True)
    fecha_terminacion = Column(String, nullable=True)

    codigo_ciiu = Column(String, nullable=True)
    supervisor = Column(String, nullable=True)
    nivel_prof_supervisor = Column(String, nullable=True)
    interventor = Column(String, nullable=True)
    nivel_prof_interventor = Column(String, nullable=True)
    cdp = Column(String, nullable=True)
    crp = Column(String, nullable=True)
    imputacion = Column(String, nullable=True)
    tiempo_adicion = Column(String, nullable=True)
    valor_final = Column(Float, nullable=True)
    forma_pago = Column(Text, nullable=True)
    objeto = Column(Text, nullable=True)
    unidad_atencion = Column(String, nullable=True)
    perfil = Column(String, nullable=True)
    municipio = Column(String, nullable=True)
    zona = Column(String, nullable=True)

    contratista = relationship("DBContratista", back_populates="contratos")
    pagos = relationship("DBPago", back_populates="contrato", cascade="all, delete-orphan")


class DBPago(Base):
    __tablename__ = "pagos"
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    contrato_id = Column(String, ForeignKey("contratos.numero_contrato"))

    tipo_informe = Column(String, nullable=True)
    periodo_desde = Column(String, nullable=True)
    periodo_hasta = Column(String, nullable=True)
    numero_pago = Column(Integer, nullable=False)
    cuentas_cobro = Column(String, nullable=True)
    valor_a_pagar = Column(Float, nullable=True)
    otro_si = Column(String, nullable=True)
    valor_pagado = Column(Float, nullable=False)
    ibc = Column(Float, nullable=True)
    periodo_cotizado = Column(String, nullable=True)

    planilla_no = Column(String, nullable=True)
    eps_nombre = Column(String, nullable=True)
    eps_valor = Column(Float, default=0.0)
    arl_nombre = Column(String, nullable=True)
    arl_valor = Column(Float, default=0.0)
    afp_nombre = Column(String, nullable=True)
    afp_valor = Column(Float, default=0.0)
    sena_valor = Column(Float, default=0.0)
    icbf_valor = Column(Float, default=0.0)
    ccf_nombre = Column(String, nullable=True)
    ccf_valor = Column(Float, default=0.0)
    valor_total_planilla = Column(Float, default=0.0)

    anexa_cert = Column(String, nullable=True)
    actividades = Column(Text, nullable=True)
    act = Column(String, nullable=True)
    observaciones = Column(Text, nullable=True)
    folios = Column(String, nullable=True)

    fecha_registro = Column(DateTime, default=datetime.utcnow)
    contrato = relationship("DBContrato", back_populates="pagos")


class DBUsuario(Base):
    __tablename__ = "usuarios"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    password_hash = Column(String)
    rol = Column(String, default="admin")