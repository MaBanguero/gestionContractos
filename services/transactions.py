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
            pagos_ordenados = sorted(c.pagos, key=lambda x: x.numero_pago)
            total_pagado = sum((p.valor_a_pagar or 0) for p in pagos_ordenados[:-1]) if pagos_ordenados else 0
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
        total_causado_acumulado = 0
        ultimo_valor_girado = 0  # Esta variable controlará el total real pagado

        for p in pagos_db:
            # REGLA DE NEGOCIO: El valor girado en este periodo es exactamente
            # lo que se había causado ANTES de registrar este pago.
            girado_en_este_periodo = total_causado_acumulado

            # Ahora sí, sumamos lo causado en este periodo al acumulado
            total_causado_acumulado += (p.valor_a_pagar or 0)

            pago_dict = {
                "id": p.id,
                "numero_pago": p.numero_pago,
                "periodo_cotizado": p.periodo_cotizado,
                "planilla_no": p.planilla_no,
                "valor_a_pagar": int(p.valor_a_pagar or 0),
                "valor_pagado_progresivo": int(girado_en_este_periodo),  # ¡Adiós al doble conteo!
                "valor_total_planilla": int(p.valor_total_planilla or 0),
                "observaciones": p.observaciones
            }
            pagos_con_acumulado.append(pago_dict)

            # Guardamos el último valor girado para enviarlo al Widget del Dashboard
            ultimo_valor_girado = girado_en_este_periodo

        valor_base_contrato = contrato.valor_final if contrato.valor_final else contrato.valor_total
        saldo_presupuestal = valor_base_contrato - total_causado_acumulado

        # Sugerencia giro es lo causado que aún no se ha girado (generalmente el último pago)
        sugerencia_giro = total_causado_acumulado - ultimo_valor_girado
        proximo_pago = (pagos_db[-1].numero_pago + 1) if pagos_db else 1

        porcentaje = (total_causado_acumulado / valor_base_contrato * 100) if valor_base_contrato > 0 else 0

        return {
            "contrato": contrato,
            "pagos": pagos_con_acumulado,
            "total_pagado": int(ultimo_valor_girado),  # Este corrige el widget superior
            "saldo": int(saldo_presupuestal),
            "porcentaje": round(porcentaje, 1),
            "proximo_pago": proximo_pago,
            "acumulado_historico_pagado": int(sugerencia_giro),
            "valor_mensual_sugerido": int(pagos_db[-1].valor_a_pagar if pagos_db else 0)
        }

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
        query = self.db.query(DBPago)

        if numero_contrato:
            query = query.filter(DBPago.contrato_id == numero_contrato)

        pagos = query.order_by(DBPago.contrato_id, DBPago.numero_pago).all()
        data = []

        for p in pagos:
            c = p.contrato

            # --- LÓGICA SINCRONIZADA CON LA PLATAFORMA ---
            valor_base_contrato = c.valor_final if c.valor_final else c.valor_total

            # 1. Total causado hasta el pago actual
            total_causado_acumulado = sum((pg.valor_a_pagar or 0) for pg in c.pagos if pg.numero_pago <= p.numero_pago)

            # 2. Saldo a Pagar: Valor total menos lo ya causado
            saldo_a_pagar = valor_base_contrato - total_causado_acumulado

            # 3. Valor Pagado (Giro): 0 en el pago 1, y la suma de causaciones anteriores en los siguientes
            valor_pagado_calculado = sum((pg.valor_a_pagar or 0) for pg in c.pagos if pg.numero_pago < p.numero_pago)

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
                "VALOR TOTAL DEL CONTRATO": int(c.valor_total) if c.valor_total else 0,
                "FECHA DE INICIO DEL CONTRATO": c.fecha_inicio,
                "FECHA TERMINACION DEL CONTRATO": c.fecha_terminacion,
                "TIEMPO DE ADICION DE CONTRATO": c.tiempo_adicion,
                "VALOR FINAL DEL CONTRATO": int(c.valor_final) if c.valor_final else 0,
                "FORMA DE PAGO": c.forma_pago,
                "PAGO No": p.numero_pago,
                "Cuentas de cobro": p.cuentas_cobro,
                "VALOR A PAGAR": int(p.valor_a_pagar) if p.valor_a_pagar else 0,
                "OTRO SI": p.otro_si,
                "VALOR PAGADO": int(valor_pagado_calculado),  # Aplicando tu regla
                "SALDO A PAGAR": int(saldo_a_pagar),
                "IBC al sistema de Seguridad Social": int(p.ibc) if p.ibc else 0,
                "PERIODO COTIZADO": p.periodo_cotizado,
                "EPS": p.eps_nombre,
                "EPS VALOR PAGADO": int(p.eps_valor) if p.eps_valor else 0,
                "ARL": p.arl_nombre,
                "ARL VALOR PAGADO": int(p.arl_valor) if p.arl_valor else 0,
                "AFP NOMBRE": p.afp_nombre,
                "AFP VALOR PAGADO": int(p.afp_valor) if p.afp_valor else 0,
                "SENA VALOR PAGADO": int(p.sena_valor) if p.sena_valor else 0,
                "ICBF VALOR PAGADO": int(p.icbf_valor) if p.icbf_valor else 0,
                "CCF": p.ccf_nombre,
                "CCF VALOR PAGADO": int(p.ccf_valor) if p.ccf_valor else 0,
                "VALOR TOTAL PLANILLA": int(p.valor_total_planilla) if p.valor_total_planilla else 0,
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

        df = pd.DataFrame(data)

        # --- CORRECCIÓN DE FORMATO CDP Y CRP ---
        def formatear_codigo(val):
            try:
                if pd.isna(val) or str(val).strip() == '' or str(val).lower() == 'nan':
                    return ''
                return str(int(float(val))).zfill(3)
            except Exception:
                return str(val).strip()

        if not df.empty:
            for col in ['CDP  No.', 'CRP No.']:
                if col in df.columns:
                    df[col] = df[col].apply(formatear_codigo)

        return df

    def importar_datos_csv(self, contenido_csv: str):
        """ Procesa el archivo CSV e inserta/actualiza usando Caché en Memoria (Upsert Seguro) """
        reader = csv.DictReader(io.StringIO(contenido_csv))
        registros = 0

        def parse_float(val):
            try:
                if not val or str(val).strip() in ['', 'N/A', 'NA', '-']:
                    return 0.0
                s = str(val).replace('$', '').replace(' ', '').strip()
                if '.' in s and ',' in s:
                    s = s.replace('.', '').replace(',', '.')
                elif '.' in s and len(s.split('.')[-1]) == 3:
                    s = s.replace('.', '')
                elif ',' in s:
                    s = s.replace(',', '.')
                return float(s)
            except Exception:
                return 0.0

        def clean_id(val):
            """ Limpia identificaciones de Excel para evitar el '.0' fantasma """
            s = str(val).strip()
            if s.endswith('.0'): return s[:-2]
            return s

        # --- MAGIA SENIOR: Cargar todo en memoria para evitar errores de tipo en SQLite ---
        cache_contratistas = {clean_id(c.identificacion): c for c in self.db.query(DBContratista).all()}
        cache_contratos = {clean_id(c.numero_contrato): c for c in self.db.query(DBContrato).all()}
        cache_pagos = {f"{clean_id(p.contrato_id)}_{p.numero_pago}": p for p in self.db.query(DBPago).all()}

        for row_cruda in reader:
            try:
                # 1. Limpieza extrema y obligatoria de cada celda del Excel
                row = {}
                for k, v in row_cruda.items():
                    if k is not None:
                        clean_k = str(k).replace('\ufeff', '').strip()
                        clean_v = str(v).strip() if v is not None else ""
                        row[clean_k] = clean_v

                identificacion = clean_id(row.get('No. DE IDENTIFICACIÓN', ''))
                numero_contrato = clean_id(row.get('N° DE CONTRATO', ''))

                if not identificacion or not numero_contrato:
                    continue

                # --- 2. UPSERT CONTRATISTA (Usando el Caché) ---
                if identificacion in cache_contratistas:
                    contratista = cache_contratistas[identificacion]
                else:
                    contratista = DBContratista(identificacion=identificacion)
                    self.db.add(contratista)
                    cache_contratistas[identificacion] = contratista

                # Asignación segura de datos (Solo si vienen llenos desde el Excel)
                if row.get('NOMBRE CONTRATISTA'): contratista.nombre = row.get('NOMBRE CONTRATISTA')
                if row.get('EXPEDIDA EN'): contratista.expedida_en = row.get('EXPEDIDA EN')
                if row.get('No. TELÉFONO y/o CELULAR'): contratista.telefono = row.get('No. TELÉFONO y/o CELULAR')
                if row.get('DIRECCION'): contratista.direccion = row.get('DIRECCION')
                if row.get('TIPO DE PERSONA'): contratista.tipo_persona = row.get('TIPO DE PERSONA')

                # --- 3. UPSERT CONTRATO (Usando el Caché) ---
                if numero_contrato in cache_contratos:
                    contrato = cache_contratos[numero_contrato]
                    contrato.contratista_id = identificacion
                else:
                    contrato = DBContrato(numero_contrato=numero_contrato, contratista_id=identificacion)
                    self.db.add(contrato)
                    cache_contratos[numero_contrato] = contrato

                if row.get('VALOR TOTAL DEL CONTRATO'): contrato.valor_total = parse_float(
                    row.get('VALOR TOTAL DEL CONTRATO'))
                if row.get('FECHA DE INICIO DEL CONTRATO'): contrato.fecha_inicio = row.get(
                    'FECHA DE INICIO DEL CONTRATO')
                if row.get('FECHA TERMINACION DEL CONTRATO'): contrato.fecha_terminacion = row.get(
                    'FECHA TERMINACION DEL CONTRATO')
                if row.get('CÓDIGO CIIU'): contrato.codigo_ciiu = row.get('CÓDIGO CIIU')
                if row.get('SUPERVISOR'): contrato.supervisor = row.get('SUPERVISOR')
                if row.get('NIVEL PROFESIONAL SUPERVISOR'): contrato.nivel_prof_supervisor = row.get(
                    'NIVEL PROFESIONAL SUPERVISOR')
                if row.get('INTERVENTOR'): contrato.interventor = row.get('INTERVENTOR')
                if row.get('NIVEL PROFESIONAL INTERVENTOR'): contrato.nivel_prof_interventor = row.get(
                    'NIVEL PROFESIONAL INTERVENTOR')
                if row.get('CDP  No.'): contrato.cdp = row.get('CDP  No.')
                if row.get('CRP No.'): contrato.crp = row.get('CRP No.')
                if row.get('IMPUTACIÓN PRESUPUESTAL'): contrato.imputacion = row.get('IMPUTACIÓN PRESUPUESTAL')
                if row.get('TIEMPO DE ADICION DE CONTRATO'): contrato.tiempo_adicion = row.get(
                    'TIEMPO DE ADICION DE CONTRATO')
                if row.get('VALOR FINAL DEL CONTRATO'): contrato.valor_final = parse_float(
                    row.get('VALOR FINAL DEL CONTRATO'))
                if row.get('FORMA DE PAGO'): contrato.forma_pago = row.get('FORMA DE PAGO')
                if row.get('OBJETO DEL CONTRATO'): contrato.objeto = row.get('OBJETO DEL CONTRATO')
                if row.get('UNIDAD DE ATENCION'): contrato.unidad_atencion = row.get('UNIDAD DE ATENCION')
                if row.get('PERFIL'): contrato.perfil = row.get('PERFIL')
                if row.get('MUNICIPIO'): contrato.municipio = row.get('MUNICIPIO')
                if row.get('ZONA'): contrato.zona = row.get('ZONA')

                # --- 4. UPSERT PAGO (Usando el Caché) ---
                pago_no_str = clean_id(row.get('PAGO No', '1'))
                pago_no = int(parse_float(pago_no_str)) if pago_no_str else 1
                pago_key = f"{numero_contrato}_{pago_no}"

                if pago_key in cache_pagos:
                    pago = cache_pagos[pago_key]
                else:
                    pago = DBPago(contrato_id=numero_contrato, numero_pago=pago_no)
                    self.db.add(pago)
                    cache_pagos[pago_key] = pago

                if row.get('TIPO DE INFORME'): pago.tipo_informe = row.get('TIPO DE INFORME')
                if row.get('PERIODO INFORME DESDE'): pago.periodo_desde = row.get('PERIODO INFORME DESDE')
                if row.get('PERIODO INFORME HASTA'): pago.periodo_hasta = row.get('PERIODO INFORME HASTA')
                if row.get('Cuentas de cobro'): pago.cuentas_cobro = row.get('Cuentas de cobro')
                if row.get('VALOR A PAGAR'): pago.valor_a_pagar = parse_float(row.get('VALOR A PAGAR'))
                if row.get('OTRO SI'): pago.otro_si = row.get('OTRO SI')
                if row.get('VALOR PAGADO'): pago.valor_pagado = parse_float(row.get('VALOR PAGADO'))
                if row.get('IBC al sistema de Seguridad Social'): pago.ibc = parse_float(
                    row.get('IBC al sistema de Seguridad Social'))
                if row.get('PERIODO COTIZADO'): pago.periodo_cotizado = row.get('PERIODO COTIZADO')
                if row.get('PLANILLA No.'): pago.planilla_no = row.get('PLANILLA No.')
                if row.get('EPS'): pago.eps_nombre = row.get('EPS')
                if row.get('EPS VALOR PAGADO'): pago.eps_valor = parse_float(row.get('EPS VALOR PAGADO'))
                if row.get('ARL'): pago.arl_nombre = row.get('ARL')
                if row.get('ARL VALOR PAGADO'): pago.arl_valor = parse_float(row.get('ARL VALOR PAGADO'))
                if row.get('AFP NOMBRE'): pago.afp_nombre = row.get('AFP NOMBRE')
                if row.get('AFP VALOR PAGADO'): pago.afp_valor = parse_float(row.get('AFP VALOR PAGADO'))
                if row.get('SENA VALOR PAGADO'): pago.sena_valor = parse_float(row.get('SENA VALOR PAGADO'))
                if row.get('ICBF VALOR PAGADO'): pago.icbf_valor = parse_float(row.get('ICBF VALOR PAGADO'))
                if row.get('CCF'): pago.ccf_nombre = row.get('CCF')
                if row.get('CCF VALOR PAGADO'): pago.ccf_valor = parse_float(row.get('CCF VALOR PAGADO'))
                if row.get('VALOR TOTAL PLANILLA'): pago.valor_total_planilla = parse_float(
                    row.get('VALOR TOTAL PLANILLA'))
                if row.get('ANEXA CERTIFICACION PARA ASIMILARSE A ASALARIADO'): pago.anexa_cert = row.get(
                    'ANEXA CERTIFICACION PARA ASIMILARSE A ASALARIADO')
                if row.get('ACTIVIDADES'): pago.actividades = row.get('ACTIVIDADES')
                if row.get('Act'): pago.act = row.get('Act')
                if row.get('OBSERVACIONES'): pago.observaciones = row.get('OBSERVACIONES')
                if row.get('N° FOLIOS'): pago.folios = row.get('N° FOLIOS')

                self.db.commit()
                registros += 1
            except Exception as e:
                self.db.rollback()
                print(f"Error procesando fila (Contrato {row.get('N° DE CONTRATO')}): {e}")
                continue

        return True, f"Importación exitosa. {registros} registros procesados y/o actualizados correctamente."

    def obtener_pago_por_id(self, pago_id: int):
        return self.db.query(DBPago).filter(DBPago.id == pago_id).first()

    def actualizar_pago_existente(self, pago_id: int, datos: dict):
        try:
            pago = self.db.query(DBPago).filter(DBPago.id == pago_id).first()
            if not pago:
                return False, "Pago no encontrado."

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

    def crear_o_actualizar_contrato(self, datos: dict):
        try:
            identificacion = str(datos.get("identificacion")).strip()
            num_contrato = str(datos.get("numero_contrato")).strip()

            # 1. CONTRATISTA: Buscar si existe
            contratista = self.db.query(DBContratista).filter(DBContratista.identificacion == identificacion).first()
            if not contratista:
                contratista = DBContratista(
                    identificacion=identificacion,
                    nombre=datos.get("nombre"),
                    expedida_en=datos.get("expedida_en"),
                    telefono=datos.get("telefono"),
                    direccion=datos.get("direccion"),
                    tipo_persona=datos.get("tipo_persona")
                )
                self.db.add(contratista)
            else:
                # Si existe, actualizamos sus datos
                contratista.nombre = datos.get("nombre", contratista.nombre)
                contratista.expedida_en = datos.get("expedida_en", contratista.expedida_en)
                contratista.telefono = datos.get("telefono", contratista.telefono)
                contratista.direccion = datos.get("direccion", contratista.direccion)
                contratista.tipo_persona = datos.get("tipo_persona", contratista.tipo_persona)

            # 2. CONTRATO: Buscar si existe
            contrato = self.db.query(DBContrato).filter(DBContrato.numero_contrato == num_contrato).first()

            # Filtramos los datos que pertenecen solo al contrato
            campos_excluidos = ["nombre", "identificacion", "expedida_en", "telefono", "direccion", "tipo_persona",
                                "numero_contrato"]
            datos_contrato = {k: v for k, v in datos.items() if k not in campos_excluidos}

            if not contrato:
                nuevo_contrato = DBContrato(numero_contrato=num_contrato, contratista_id=identificacion,
                                            **datos_contrato)
                self.db.add(nuevo_contrato)
            else:
                # Si existe, actualizamos los campos del contrato
                for key, value in datos_contrato.items():
                    if hasattr(contrato, key):
                        setattr(contrato, key, value)
                contrato.contratista_id = identificacion

            self.db.commit()
            return True, "Información del contrato guardada exitosamente."
        except SQLAlchemyError as e:
            self.db.rollback()
            return False, f"Error de BD: {str(e)}"