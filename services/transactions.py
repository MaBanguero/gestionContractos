from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from models.db_models import DBContratista, DBContrato, DBPago
import pandas as pd
import csv
import io


class GestorTransacciones:
    """ Clase modular para encapsular toda la lógica de base de datos """

    def __init__(self, db: Session):
        self.db = db

    def obtener_resumen_dashboard(self):
        contratos = self.db.query(DBContrato).all()
        lista = []
        for c in contratos:
            total_pagado = sum(p.valor_pagado for p in c.pagos)
            porcentaje = (total_pagado / c.valor_total * 100) if c.valor_total > 0 else 0
            lista.append({
                "numero_contrato": c.numero_contrato,
                "contratista": c.contratista.nombre,
                "valor_total": c.valor_total,
                "total_pagado": total_pagado,
                "saldo": c.valor_total - total_pagado,
                "porcentaje_pagado": round(porcentaje, 1)
            })
        return lista

    def obtener_detalle_contrato(self, numero_contrato: str):
        contrato = self.db.query(DBContrato).filter(DBContrato.numero_contrato == numero_contrato).first()
        if not contrato:
            return None

        pagos_db = self.db.query(DBPago).filter(DBPago.contrato_id == numero_contrato).order_by(
            DBPago.numero_pago.asc()).all()

        pagos_con_acumulado = []
        acumulado_progresivo = 0
        total_causado_acumulado = 0

        for p in pagos_db:
            acumulado_progresivo += p.valor_pagado
            total_causado_acumulado += p.valor_a_pagar

            pago_dict = {
                "id": p.id,
                "numero_pago": p.numero_pago,
                "periodo_cotizado": p.periodo_cotizado,
                "planilla_no": p.planilla_no,
                "valor_a_pagar": int(p.valor_a_pagar),
                "valor_pagado_progresivo": int(acumulado_progresivo),
                "valor_total_planilla": int(p.valor_total_planilla),
                "observaciones": p.observaciones
            }
            pagos_con_acumulado.append(pago_dict)

        # LÓGICA DE SALDO DISPONIBLE CORREGIDA:
        # El saldo real es el Valor Final del contrato MENOS lo que ya se facturó/causó,
        # sin importar si ya se le giró el dinero o no.
        valor_base_contrato = contrato.valor_final if contrato.valor_final else contrato.valor_total
        saldo_presupuestal = valor_base_contrato - total_causado_acumulado

        sugerencia_giro = total_causado_acumulado - acumulado_progresivo
        proximo_pago = (pagos_db[-1].numero_pago + 1) if pagos_db else 1

        # El porcentaje de ejecución del contrato debe medirse por el trabajo realizado (Causado)
        porcentaje = (total_causado_acumulado / valor_base_contrato * 100) if valor_base_contrato > 0 else 0

        return {
            "contrato": contrato,
            "pagos": pagos_con_acumulado,
            "total_pagado": int(acumulado_progresivo),
            "saldo": int(saldo_presupuestal),  # <--- Aquí enviamos el saldo corregido
            "porcentaje": round(porcentaje, 1),
            "proximo_pago": proximo_pago,
            "acumulado_historico_pagado": int(sugerencia_giro),
            "valor_mensual_sugerido": int(pagos_db[-1].valor_a_pagar if pagos_db else 0)
        }

    def crear_o_actualizar_contrato(self, datos: dict):
        try:
            identificacion = datos.get("identificacion")
            num_contrato = datos.get("numero_contrato")

            # 1. Contratista
            contratista = self.db.query(DBContratista).filter(DBContratista.identificacion == identificacion).first()
            if not contratista:
                contratista = DBContratista(
                    identificacion=identificacion, nombre=datos.get("nombre"),
                    expedida_en=datos.get("expedida_en"), telefono=datos.get("telefono"),
                    direccion=datos.get("direccion"), tipo_persona=datos.get("tipo_persona")
                )
                self.db.add(contratista)

            # 2. Contrato
            if not self.db.query(DBContrato).filter(DBContrato.numero_contrato == num_contrato).first():
                nuevo_contrato = DBContrato(**{k: v for k, v in datos.items() if
                                               k not in ["nombre", "identificacion", "expedida_en", "telefono",
                                                         "direccion", "tipo_persona"]})
                nuevo_contrato.contratista_id = identificacion
                self.db.add(nuevo_contrato)

            self.db.commit()
            return True, "Contrato guardado exitosamente."
        except SQLAlchemyError as e:
            self.db.rollback()
            return False, f"Error de BD: {str(e)}"

    def registrar_pago_supervision(self, datos: dict):
        try:
            nuevo_pago = DBPago(**datos)
            self.db.add(nuevo_pago)
            self.db.commit()
            return True, f"Pago N° {datos.get('numero_pago')} registrado correctamente."
        except SQLAlchemyError as e:
            self.db.rollback()
            return False, f"Error al registrar pago: {str(e)}"

    def generar_excel_supervisiones(self, numero_contrato: str = None):
        """ Genera el Excel. Si recibe numero_contrato, filtra solo ese. Si no, exporta todos. """

        # Iniciamos la consulta base
        query = self.db.query(DBPago)

        # Aplicamos el filtro si el usuario solicitó un contrato específico
        if numero_contrato:
            query = query.filter(DBPago.contrato_id == numero_contrato)

        # Ejecutamos la consulta ordenando los datos
        pagos = query.order_by(DBPago.contrato_id, DBPago.numero_pago).all()

        data = []

        for p in pagos:
            c = p.contrato
            total_historico = sum(pg.valor_pagado for pg in c.pagos if pg.numero_pago <= p.numero_pago)
            saldo_a_pagar = c.valor_total - total_historico

            data.append({
                "TIPO DE INFORME": p.tipo_informe,
                "N° DE CONTRATO": c.numero_contrato,
                "PERIODO INFORME DESDE": p.periodo_desde,
                "PERIODO INFORME HASTA": p.periodo_hasta,
                "NOMBRE CONTRATISTA": c.contratista.nombre,
                "No. DE IDENTIFICACIÓN": c.contratista.identificacion,
                "EXPEDIDA EN": c.contratista.expedida_en,
                "No. TELÉFONO y/o CELULAR": c.contratista.telefono,
                "DIRECCION": c.contratista.direccion,
                "TIPO DE PERSONA": c.contratista.tipo_persona,
                "CÓDIGO CIIU": c.codigo_ciiu,
                "SUPERVISOR": c.supervisor,
                "NIVEL PROFESIONAL SUPERVISOR": c.nivel_prof_supervisor,
                "INTERVENTOR": c.interventor,
                "NIVEL PROFESIONAL INTERVENTOR": c.nivel_prof_interventor,
                "CDP  No.": c.cdp,
                "CRP No.": c.crp,
                "IMPUTACIÓN PRESUPUESTAL": c.imputacion,
                "VALOR TOTAL DEL CONTRATO": c.valor_total,
                "FECHA DE INICIO DEL CONTRATO": c.fecha_inicio,
                "FECHA TERMINACION DEL CONTRATO": c.fecha_terminacion,
                "TIEMPO DE ADICION DE CONTRATO": c.tiempo_adicion,
                "VALOR FINAL DEL CONTRATO": c.valor_final,
                "FORMA DE PAGO": c.forma_pago,
                "PAGO No": p.numero_pago,
                "Cuentas de cobro": p.cuentas_cobro,
                "VALOR A PAGAR": p.valor_a_pagar,
                "OTRO SI": p.otro_si,
                "VALOR PAGADO": p.valor_pagado,
                "SALDO A PAGAR": saldo_a_pagar,
                "IBC al sistema de Seguridad Social": p.ibc,
                "PERIODO COTIZADO": p.periodo_cotizado,
                "EPS": p.eps_nombre,
                "EPS VALOR PAGADO": p.eps_valor,
                "ARL": p.arl_nombre,
                "ARL VALOR PAGADO": p.arl_valor,
                "AFP NOMBRE": p.afp_nombre,
                "AFP VALOR PAGADO": p.afp_valor,
                "SENA VALOR PAGADO": p.sena_valor,
                "ICBF VALOR PAGADO": p.icbf_valor,
                "CCF": p.ccf_nombre,
                "CCF VALOR PAGADO": p.ccf_valor,
                "VALOR TOTAL PLANILLA": p.valor_total_planilla,
                "PLANILLA No.": p.planilla_no,
                "ANEXA CERTIFICACION PARA ASIMILARSE A ASALARIADO": p.anexa_cert,
                "OBJETO DEL CONTRATO": c.objeto,
                "ACTIVIDADES": p.actividades,
                "Act": p.act,
                "OBSERVACIONES": p.observaciones,
                "N° FOLIOS": p.folios,
                "UNIDAD DE ATENCION": c.unidad_atencion,
                "PERFIL": c.perfil,
                "MUNICIPIO": c.municipio,
                "ZONA": c.zona
            })

        return pd.DataFrame(data)

    def importar_datos_csv(self, contenido_csv: str):
        """ Procesa el archivo CSV e inserta TODAS las 54 columnas modularmente """
        reader = csv.DictReader(io.StringIO(contenido_csv))
        registros = 0

        # --- PARSER DE NÚMEROS A PRUEBA DE ERRORES ---
        def parse_float(val):
            try:
                if not val or str(val).strip() in ['', 'N/A', 'NA', '-']:
                    return 0.0

                # 1. Limpiamos signos de moneda y espacios
                s = str(val).replace('$', '').replace(' ', '').strip()

                # 2. Caso: Formato Latino explícito (ej: 1.234.567,89)
                if '.' in s and ',' in s:
                    s = s.replace('.', '').replace(',', '.')

                # 3. Caso: Solo puntos como miles (ej: 2.800.000)
                elif '.' in s and len(s.split('.')[-1]) == 3:
                    s = s.replace('.', '')

                # 4. Caso: Solo coma como decimal (ej: 2800000,50)
                elif ',' in s:
                    s = s.replace(',', '.')

                return float(s)
            except Exception as e:
                return 0.0

        # ----------------------------------------------------

        for row in reader:
            try:
                identificacion = str(row.get('No. DE IDENTIFICACIÓN', '')).strip()
                numero_contrato = str(row.get('N° DE CONTRATO', '')).strip()
                if not identificacion or not numero_contrato: continue

                # 1. Crear Contratista con todos sus datos
                if not self.db.query(DBContratista).filter(DBContratista.identificacion == identificacion).first():
                    self.db.add(DBContratista(
                        identificacion=identificacion,
                        nombre=row.get('NOMBRE CONTRATISTA', ''),
                        expedida_en=row.get('EXPEDIDA EN', ''),
                        telefono=row.get('No. TELÉFONO y/o CELULAR', ''),
                        direccion=row.get('DIRECCION', ''),
                        tipo_persona=row.get('TIPO DE PERSONA', '')
                    ))

                # 2. Crear Contrato con todos sus datos
                if not self.db.query(DBContrato).filter(DBContrato.numero_contrato == numero_contrato).first():
                    self.db.add(DBContrato(
                        numero_contrato=numero_contrato,
                        contratista_id=identificacion,
                        valor_total=parse_float(row.get('VALOR TOTAL DEL CONTRATO', 0)),
                        fecha_inicio=row.get('FECHA DE INICIO DEL CONTRATO', ''),
                        fecha_terminacion=row.get('FECHA TERMINACION DEL CONTRATO', ''),
                        codigo_ciiu=row.get('CÓDIGO CIIU', ''),
                        supervisor=row.get('SUPERVISOR', ''),
                        nivel_prof_supervisor=row.get('NIVEL PROFESIONAL SUPERVISOR', ''),
                        interventor=row.get('INTERVENTOR', ''),
                        nivel_prof_interventor=row.get('NIVEL PROFESIONAL INTERVENTOR', ''),
                        cdp=row.get('CDP  No.', ''),
                        crp=row.get('CRP No.', ''),
                        imputacion=row.get('IMPUTACIÓN PRESUPUESTAL', ''),
                        tiempo_adicion=row.get('TIEMPO DE ADICION DE CONTRATO', ''),
                        valor_final=parse_float(row.get('VALOR FINAL DEL CONTRATO', 0)),
                        forma_pago=row.get('FORMA DE PAGO', ''),
                        objeto=row.get('OBJETO DEL CONTRATO', ''),
                        unidad_atencion=row.get('UNIDAD DE ATENCION', ''),
                        perfil=row.get('PERFIL', ''),
                        municipio=row.get('MUNICIPIO', ''),
                        zona=row.get('ZONA', '')
                    ))

                # 3. Registrar el Pago y la Supervisión con todos los campos
                pago_no_str = str(row.get('PAGO No', '1')).strip()
                pago_no = int(parse_float(pago_no_str)) if pago_no_str else 1

                if not self.db.query(DBPago).filter(DBPago.contrato_id == numero_contrato,
                                                    DBPago.numero_pago == pago_no).first():
                    self.db.add(DBPago(
                        contrato_id=numero_contrato,
                        numero_pago=pago_no,
                        tipo_informe=row.get('TIPO DE INFORME', ''),
                        periodo_desde=row.get('PERIODO INFORME DESDE', ''),
                        periodo_hasta=row.get('PERIODO INFORME HASTA', ''),
                        cuentas_cobro=row.get('Cuentas de cobro', ''),
                        valor_a_pagar=parse_float(row.get('VALOR A PAGAR', 0)),
                        otro_si=row.get('OTRO SI', ''),
                        valor_pagado=parse_float(row.get('VALOR PAGADO', 0)),
                        ibc=parse_float(row.get('IBC al sistema de Seguridad Social', 0)),
                        periodo_cotizado=str(row.get('PERIODO COTIZADO', '')),
                        planilla_no=str(row.get('PLANILLA No.', '')),
                        eps_nombre=str(row.get('EPS', '')),
                        eps_valor=parse_float(row.get('EPS VALOR PAGADO', 0)),
                        arl_nombre=str(row.get('ARL', '')),
                        arl_valor=parse_float(row.get('ARL VALOR PAGADO', 0)),
                        afp_nombre=str(row.get('AFP NOMBRE', '')),
                        afp_valor=parse_float(row.get('AFP VALOR PAGADO', 0)),
                        sena_valor=parse_float(row.get('SENA VALOR PAGADO', 0)),
                        icbf_valor=parse_float(row.get('ICBF VALOR PAGADO', 0)),
                        ccf_nombre=str(row.get('CCF', '')),
                        ccf_valor=parse_float(row.get('CCF VALOR PAGADO', 0)),
                        valor_total_planilla=parse_float(row.get('VALOR TOTAL PLANILLA', 0)),
                        anexa_cert=str(row.get('ANEXA CERTIFICACION PARA ASIMILARSE A ASALARIADO', '')),
                        actividades=row.get('ACTIVIDADES', ''),
                        act=str(row.get('Act', '')),
                        observaciones=row.get('OBSERVACIONES', ''),
                        folios=str(row.get('N° FOLIOS', ''))
                    ))
                self.db.commit()
                registros += 1
            except Exception as e:
                self.db.rollback()
                print(f"Error procesando fila: {e}")
                continue

        return True, f"Importación exitosa. {registros} registros procesados."

    def obtener_pago_por_id(self, pago_id: int):
        return self.db.query(DBPago).filter(DBPago.id == pago_id).first()

    def actualizar_pago_existente(self, pago_id: int, datos: dict):
        try:
            pago = self.db.query(DBPago).filter(DBPago.id == pago_id).first()
            if not pago:
                return False, "Pago no encontrado."

            # Actualizamos los campos dinámicamente
            for key, value in datos.items():
                if hasattr(pago, key):
                    setattr(pago, key, value)

            self.db.commit()
            return True, "Registro actualizado correctamente."
        except Exception as e:
            self.db.rollback()
            return False, f"Error al actualizar: {str(e)}"

    def eliminar_pago(self, pago_id: int):
        try:
            pago = self.db.query(DBPago).filter(DBPago.id == pago_id).first()
            if not pago:
                return False, "El pago no existe."

            self.db.delete(pago)
            self.db.commit()
            return True, "Pago eliminado exitosamente. El saldo ha sido recalculado."
        except Exception as e:
            self.db.rollback()
            return False, f"Error al eliminar: {str(e)}"

