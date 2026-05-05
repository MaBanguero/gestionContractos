from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import or_
from models.db_models import DBContratista, DBContrato, DBPago, DBPerfil, DBActividadPerfil
import pandas as pd
import csv
import io


class GestorTransacciones:
    """ Clase modular para encapsular toda la lógica de base de datos """

    def __init__(self, db: Session):
        self.db = db

    def obtener_resumen_dashboard(self, busqueda: str = None, tipo_filtro: str = "todos", solo_inactivos: bool = False):
        """Retorna el resumen de contratos, aplicando un filtro global o específico multicriterio."""
        query = self.db.query(DBContrato).join(DBContrato.contratista)

        # LÓGICA DE BÚSQUEDA (Busca en TODOS sin importar estado si el usuario teclea algo)
        if busqueda:
            terminos = busqueda.strip().split()
            for termino in terminos:
                t = f"%{termino}%"
                if tipo_filtro == "identificacion":
                    query = query.filter(DBContratista.identificacion.ilike(t))
                elif tipo_filtro == "nombre":
                    query = query.filter(DBContratista.nombre.ilike(t))
                elif tipo_filtro == "numero_contrato":
                    query = query.filter(DBContrato.numero_contrato.ilike(t))
                elif tipo_filtro == "resolucion":
                    query = query.filter(DBContrato.resolucion.ilike(t))
                elif tipo_filtro == "tipologia":
                    query = query.filter(DBContrato.tipologia.ilike(t))
                else:
                    query = query.filter(
                        or_(
                            DBContratista.nombre.ilike(t),
                            DBContratista.identificacion.ilike(t),
                            DBContrato.numero_contrato.ilike(t),
                            DBContrato.resolucion.ilike(t),
                            DBContrato.tipologia.ilike(t)
                        )
                    )
        else:
            # LÓGICA DE VISTAS ESTÁTICAS (Separa activos de inactivos)
            if solo_inactivos:
                query = query.filter(DBContrato.estado == "INACTIVO")
            else:
                # Contratos activos o heredados (NULL)
                query = query.filter((DBContrato.estado == "ACTIVO") | (DBContrato.estado == None))

        contratos = query.all()

        # Bulk query: obtener TODAS las resoluciones de cada contratista (sin importar estado)
        contratista_ids = list({c.contratista_id for c in contratos})
        todas_resoluciones = (
            self.db.query(DBContrato.contratista_id, DBContrato.resolucion)
            .filter(DBContrato.contratista_id.in_(contratista_ids))
            .filter(DBContrato.resolucion != None)
            .filter(DBContrato.resolucion != "")
            .distinct()
            .all()
        ) if contratista_ids else []

        resoluciones_map = {}
        for cid, res in todas_resoluciones:
            if res and res.strip():
                resoluciones_map.setdefault(cid, [])
                if res.strip() not in resoluciones_map[cid]:
                    resoluciones_map[cid].append(res.strip())

        lista = []
        for c in contratos:
            pagos_ordenados = sorted(c.pagos, key=lambda x: x.numero_pago)
            total_pagado = sum((p.valor_a_pagar or 0) for p in pagos_ordenados[:-1]) if pagos_ordenados else 0
            porcentaje = (total_pagado / c.valor_total * 100) if c.valor_total > 0 else 0

            lista.append({
                "numero_contrato": c.numero_contrato,
                "identificacion": c.contratista_id,
                "contratista": c.contratista.nombre,
                "perfil": c.perfil or "N/A",
                "resolucion": c.resolucion or "N/A",
                "tipologia": c.tipologia or "N/A",
                "estado": c.estado or "ACTIVO",
                "valor_total": float(c.valor_total),
                "total_pagado": float(total_pagado),
                "saldo": float(c.valor_total - total_pagado),
                "porcentaje_pagado": round(porcentaje, 1),
                "resoluciones_contratista": resoluciones_map.get(c.contratista_id, [])
            })
        return lista

    def cambiar_estado_contrato(self, numero_contrato: str, nuevo_estado: str):
        """Activa o inactiva (archiva) un contrato lógicamente (Soft Delete)."""
        try:
            contrato = self.db.query(DBContrato).filter(DBContrato.numero_contrato == numero_contrato).first()
            if contrato:
                contrato.estado = nuevo_estado
                self.db.commit()
                accion = 'Archivado' if nuevo_estado == 'INACTIVO' else 'Restaurado'
                return True, f"El contrato ha sido {accion} exitosamente."
            return False, "Contrato no encontrado."
        except Exception as e:
            self.db.rollback()
            return False, str(e)

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
        """ Procesa el archivo CSV e inserta/actualiza TODAS las columnas modularmente """
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
            except Exception as e:
                return 0.0

        for row_cruda in reader:
            try:
                # --- MAGIA SENIOR: Limpiar espacios invisibles y caracteres BOM de Excel ---
                row = {str(k).replace('\ufeff', '').strip(): v for k, v in row_cruda.items() if k is not None}
                # -------------------------------------------------------------------------------

                identificacion = str(row.get('No. DE IDENTIFICACIÓN', '')).strip()
                numero_contrato = str(row.get('N° DE CONTRATO', '')).strip()

                if not identificacion or not numero_contrato:
                    continue

                from models.db_models import DBContratista, DBContrato, \
                    DBPago  # Importaciones seguras si el archivo lo requiere

                # --- 1. UPSERT CONTRATISTA ---
                contratista = self.db.query(DBContratista).filter(
                    DBContratista.identificacion == identificacion).first()
                if not contratista:
                    contratista = DBContratista(identificacion=identificacion)
                    self.db.add(contratista)

                if row.get('NOMBRE CONTRATISTA'): contratista.nombre = row.get('NOMBRE CONTRATISTA', '')
                if row.get('EXPEDIDA EN'): contratista.expedida_en = row.get('EXPEDIDA EN', '')
                if row.get('No. TELÉFONO y/o CELULAR'): contratista.telefono = row.get('No. TELÉFONO y/o CELULAR', '')
                if row.get('DIRECCION'): contratista.direccion = row.get('DIRECCION', '')
                if row.get('TIPO DE PERSONA'): contratista.tipo_persona = row.get('TIPO DE PERSONA', '')

                # --- 2. UPSERT CONTRATO ---
                contrato = self.db.query(DBContrato).filter(DBContrato.numero_contrato == numero_contrato).first()
                if not contrato:
                    contrato = DBContrato(numero_contrato=numero_contrato, contratista_id=identificacion)
                    self.db.add(contrato)
                else:
                    contrato.contratista_id = identificacion

                if row.get('VALOR TOTAL DEL CONTRATO'): contrato.valor_total = parse_float(
                    row.get('VALOR TOTAL DEL CONTRATO', 0))
                if row.get('FECHA DE INICIO DEL CONTRATO'): contrato.fecha_inicio = row.get(
                    'FECHA DE INICIO DEL CONTRATO', '')
                if row.get('FECHA TERMINACION DEL CONTRATO'): contrato.fecha_terminacion = row.get(
                    'FECHA TERMINACION DEL CONTRATO', '')
                if row.get('CÓDIGO CIIU'): contrato.codigo_ciiu = row.get('CÓDIGO CIIU', '')
                if row.get('SUPERVISOR'): contrato.supervisor = row.get('SUPERVISOR', '')
                if row.get('NIVEL PROFESIONAL SUPERVISOR'): contrato.nivel_prof_supervisor = row.get(
                    'NIVEL PROFESIONAL SUPERVISOR', '')
                if row.get('INTERVENTOR'): contrato.interventor = row.get('INTERVENTOR', '')
                if row.get('NIVEL PROFESIONAL INTERVENTOR'): contrato.nivel_prof_interventor = row.get(
                    'NIVEL PROFESIONAL INTERVENTOR', '')
                if row.get('CDP  No.'): contrato.cdp = row.get('CDP  No.', '')
                if row.get('CRP No.'): contrato.crp = row.get('CRP No.', '')
                if row.get('IMPUTACIÓN PRESUPUESTAL'): contrato.imputacion = row.get('IMPUTACIÓN PRESUPUESTAL', '')
                if row.get('TIEMPO DE ADICION DE CONTRATO'): contrato.tiempo_adicion = row.get(
                    'TIEMPO DE ADICION DE CONTRATO', '')
                if row.get('VALOR FINAL DEL CONTRATO'): contrato.valor_final = parse_float(
                    row.get('VALOR FINAL DEL CONTRATO', 0))
                if row.get('FORMA DE PAGO'): contrato.forma_pago = row.get('FORMA DE PAGO', '')
                if row.get('OBJETO DEL CONTRATO'): contrato.objeto = row.get('OBJETO DEL CONTRATO', '')
                if row.get('UNIDAD DE ATENCION'): contrato.unidad_atencion = row.get('UNIDAD DE ATENCION', '')
                if row.get('PERFIL'): contrato.perfil = row.get('PERFIL', '')
                if row.get('MUNICIPIO'): contrato.municipio = row.get('MUNICIPIO', '')
                if row.get('ZONA'): contrato.zona = row.get('ZONA', '')

                # --- NUEVOS CAMPOS ---
                # Asume que las columnas en Excel se llamarán "RESOLUCION" y "TIPOLOGIA"
                if row.get('RESOLUCION'): contrato.resolucion = row.get('RESOLUCION', '')
                if row.get('TIPOLOGIA'): contrato.tipologia = row.get('TIPOLOGIA', '')

                # --- 3. UPSERT PAGO ---
                pago_no_str = str(row.get('PAGO No', '1')).strip()
                pago_no = int(parse_float(pago_no_str)) if pago_no_str else 1

                pago = self.db.query(DBPago).filter(DBPago.contrato_id == numero_contrato,
                                                    DBPago.numero_pago == pago_no).first()
                if not pago:
                    pago = DBPago(contrato_id=numero_contrato, numero_pago=pago_no)
                    self.db.add(pago)

                if row.get('TIPO DE INFORME'): pago.tipo_informe = row.get('TIPO DE INFORME', '')
                if row.get('PERIODO INFORME DESDE'): pago.periodo_desde = row.get('PERIODO INFORME DESDE', '')
                if row.get('PERIODO INFORME HASTA'): pago.periodo_hasta = row.get('PERIODO INFORME HASTA', '')
                if row.get('Cuentas de cobro'): pago.cuentas_cobro = row.get('Cuentas de cobro', '')
                if row.get('VALOR A PAGAR'): pago.valor_a_pagar = parse_float(row.get('VALOR A PAGAR', 0))
                if row.get('OTRO SI'): pago.otro_si = row.get('OTRO SI', '')
                if row.get('VALOR PAGADO'): pago.valor_pagado = parse_float(row.get('VALOR PAGADO', 0))
                if row.get('IBC al sistema de Seguridad Social'): pago.ibc = parse_float(
                    row.get('IBC al sistema de Seguridad Social', 0))
                if row.get('PERIODO COTIZADO'): pago.periodo_cotizado = str(row.get('PERIODO COTIZADO', ''))
                if row.get('PLANILLA No.'): pago.planilla_no = str(row.get('PLANILLA No.', ''))
                if row.get('EPS'): pago.eps_nombre = str(row.get('EPS', ''))
                if row.get('EPS VALOR PAGADO'): pago.eps_valor = parse_float(row.get('EPS VALOR PAGADO', 0))
                if row.get('ARL'): pago.arl_nombre = str(row.get('ARL', ''))
                if row.get('ARL VALOR PAGADO'): pago.arl_valor = parse_float(row.get('ARL VALOR PAGADO', 0))
                if row.get('AFP NOMBRE'): pago.afp_nombre = str(row.get('AFP NOMBRE', ''))
                if row.get('AFP VALOR PAGADO'): pago.afp_valor = parse_float(row.get('AFP VALOR PAGADO', 0))
                if row.get('SENA VALOR PAGADO'): pago.sena_valor = parse_float(row.get('SENA VALOR PAGADO', 0))
                if row.get('ICBF VALOR PAGADO'): pago.icbf_valor = parse_float(row.get('ICBF VALOR PAGADO', 0))
                if row.get('CCF'): pago.ccf_nombre = str(row.get('CCF', ''))
                if row.get('CCF VALOR PAGADO'): pago.ccf_valor = parse_float(row.get('CCF VALOR PAGADO', 0))
                if row.get('VALOR TOTAL PLANILLA'): pago.valor_total_planilla = parse_float(
                    row.get('VALOR TOTAL PLANILLA', 0))
                if row.get('ANEXA CERTIFICACION PARA ASIMILARSE A ASALARIADO'): pago.anexa_cert = str(
                    row.get('ANEXA CERTIFICACION PARA ASIMILARSE A ASALARIADO', ''))
                if row.get('ACTIVIDADES'): pago.actividades = row.get('ACTIVIDADES', '')
                if row.get('Act'): pago.act = str(row.get('Act', ''))
                if row.get('OBSERVACIONES'): pago.observaciones = row.get('OBSERVACIONES', '')
                if row.get('N° FOLIOS'): pago.folios = str(row.get('N° FOLIOS', ''))

                self.db.commit()
                registros += 1
            except Exception as e:
                self.db.rollback()
                print(f"Error procesando fila: {e}")
                continue

        return True, f"Importación exitosa. {registros} registros procesados y/o actualizados."

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

    def crear_o_actualizar_contrato(self, form_data: dict):
        """
        Registra un nuevo contrato o actualiza uno existente desde la UI.
        Maneja la integridad referencial con el Contratista (Upsert).
        """
        try:
            identificacion = str(form_data.get('identificacion', '')).strip()
            numero_contrato = str(form_data.get('numero_contrato', '')).strip()

            if not identificacion or not numero_contrato:
                return False, "La Identificación del contratista y el Número de Contrato son obligatorios."

            # 1. Lógica Upsert para el Contratista
            contratista = self.db.query(DBContratista).filter(DBContratista.identificacion == identificacion).first()
            if not contratista:
                contratista = DBContratista(identificacion=identificacion)
                self.db.add(contratista)

            contratista.nombre = form_data.get('nombre', contratista.nombre)
            contratista.expedida_en = form_data.get('expedida_en', contratista.expedida_en)
            contratista.telefono = form_data.get('telefono', contratista.telefono)
            contratista.direccion = form_data.get('direccion', contratista.direccion)
            contratista.tipo_persona = form_data.get('tipo_persona', contratista.tipo_persona)

            # 2. Lógica Upsert para el Contrato
            contrato = self.db.query(DBContrato).filter(DBContrato.numero_contrato == numero_contrato).first()
            es_nuevo = False

            if not contrato:
                contrato = DBContrato(numero_contrato=numero_contrato)
                self.db.add(contrato)
                es_nuevo = True

            # Asignación de llaves foráneas y metadatos
            contrato.contratista_id = contratista.identificacion
            contrato.perfil = form_data.get('perfil', contrato.perfil)
            contrato.supervisor = form_data.get('supervisor', contrato.supervisor)
            contrato.nivel_prof_supervisor = form_data.get('nivel_prof_supervisor', contrato.nivel_prof_supervisor)
            contrato.interventor = form_data.get('interventor', contrato.interventor)
            contrato.cdp = form_data.get('cdp', contrato.cdp)
            contrato.crp = form_data.get('crp', contrato.crp)
            contrato.imputacion = form_data.get('imputacion', contrato.imputacion)
            contrato.codigo_ciiu = form_data.get('codigo_ciiu', contrato.codigo_ciiu)
            contrato.forma_pago = form_data.get('forma_pago', contrato.forma_pago)
            contrato.objeto = form_data.get('objeto', contrato.objeto)

            # Fechas y tiempos
            contrato.fecha_inicio = form_data.get('fecha_inicio', contrato.fecha_inicio)
            contrato.fecha_terminacion = form_data.get('fecha_terminacion', contrato.fecha_terminacion)
            contrato.tiempo_adicion = form_data.get('tiempo_adicion', contrato.tiempo_adicion)

            # Lógica financiera
            contrato.valor_total = float(form_data.get('valor_total') or 0.0)
            contrato.valor_final = float(form_data.get('valor_final') or contrato.valor_total)

            # Campos: Resolucion y Tipología
            contrato.resolucion = form_data.get('resolucion', contrato.resolucion)
            contrato.tipologia = form_data.get('tipologia', contrato.tipologia)

            # Confirmación de la transacción ACID
            self.db.commit()
            accion = "creado" if es_nuevo else "actualizado"
            return True, f"El Contrato {numero_contrato} ha sido {accion} exitosamente."

        except Exception as e:
            self.db.rollback()
            return False, f"Error crítico en la transacción de base de datos: {str(e)}"

    def obtener_perfiles(self):
        return self.db.query(DBPerfil).order_by(DBPerfil.nombre).all()

    def obtener_perfil(self, perfil_id: int):
        return self.db.query(DBPerfil).filter(DBPerfil.id == perfil_id).first()

    def crear_perfil(self, nombre: str, descripcion: str = "", honorario_referencia: float = 0.0):
        try:
            nuevo = DBPerfil(
                nombre=nombre.strip().upper(),
                descripcion=descripcion,
                honorario_referencia=honorario_referencia
            )
            self.db.add(nuevo)
            self.db.commit()
            return True, "Perfil creado exitosamente."
        except Exception as e:
            self.db.rollback()
            return False, f"Error al crear perfil (¿Nombre duplicado?): {str(e)}"

    def editar_perfil(self, perfil_id: int, nombre: str, descripcion: str, honorario_referencia: float):
        """Actualiza los metadatos principales de un perfil, incluyendo su honorario base."""
        try:
            perfil = self.db.query(DBPerfil).filter(DBPerfil.id == perfil_id).first()
            if perfil:
                perfil.nombre = nombre.strip().upper()
                perfil.descripcion = descripcion
                perfil.honorario_referencia = honorario_referencia
                self.db.commit()
                return True, "Perfil y honorario actualizados correctamente."
            return False, "Perfil no encontrado."
        except Exception as e:
            self.db.rollback()
            return False, str(e)

    def eliminar_perfil(self, perfil_id: int):
        try:
            perfil = self.db.query(DBPerfil).filter(DBPerfil.id == perfil_id).first()
            if perfil:
                self.db.delete(perfil)
                self.db.commit()
                return True, "Perfil y sus actividades eliminados."
            return False, "Perfil no encontrado."
        except Exception as e:
            self.db.rollback()
            return False, str(e)

    def agregar_actividad(self, perfil_id: int, descripcion: str, orden: int = 0):
        try:
            actividad = DBActividadPerfil(perfil_id=perfil_id, descripcion=descripcion.strip(), orden=orden)
            self.db.add(actividad)
            self.db.commit()
            return True, "Actividad agregada."
        except Exception as e:
            self.db.rollback()
            return False, str(e)

    def eliminar_actividad(self, actividad_id: int):
        try:
            actividad = self.db.query(DBActividadPerfil).filter(DBActividadPerfil.id == actividad_id).first()
            if actividad:
                self.db.delete(actividad)
                self.db.commit()
                return True, "Actividad eliminada."
            return False, "Actividad no encontrada."
        except Exception as e:
            self.db.rollback()
            return False, str(e)

    def obtener_actividad(self, actividad_id: int):
        """Recupera una actividad específica por su ID."""
        return self.db.query(DBActividadPerfil).filter(DBActividadPerfil.id == actividad_id).first()

    def buscar_contratistas(self, q: str):
        """Busca contratistas por identificación o nombre (máx. 10 resultados)."""
        t = f"%{q}%"
        return (
            self.db.query(DBContratista)
            .filter(or_(DBContratista.identificacion.ilike(t), DBContratista.nombre.ilike(t)))
            .order_by(DBContratista.nombre)
            .limit(10)
            .all()
        )

    def obtener_contratista(self, identificacion: str):
        return self.db.query(DBContratista).filter(DBContratista.identificacion == identificacion).first()

    def actualizar_contratista(self, identificacion: str, datos: dict):
        try:
            contratista = self.db.query(DBContratista).filter(DBContratista.identificacion == identificacion).first()
            if not contratista:
                return False, "Contratista no encontrado."
            contratista.nombre = datos.get('nombre', contratista.nombre)
            contratista.expedida_en = datos.get('expedida_en', contratista.expedida_en)
            contratista.telefono = datos.get('telefono', contratista.telefono)
            contratista.direccion = datos.get('direccion', contratista.direccion)
            contratista.tipo_persona = datos.get('tipo_persona', contratista.tipo_persona)
            self.db.commit()
            return True, "Datos del contratista actualizados correctamente."
        except Exception as e:
            self.db.rollback()
            return False, str(e)

    def editar_actividad(self, actividad_id: int, descripcion: str, orden: int):
        """Actualiza el contenido y el orden de una obligación existente."""
        try:
            actividad = self.db.query(DBActividadPerfil).filter(DBActividadPerfil.id == actividad_id).first()
            if actividad:
                actividad.descripcion = descripcion.strip()
                actividad.orden = orden
                self.db.commit()
                return True, "Obligación actualizada correctamente."
            return False, "Actividad no encontrada."
        except Exception as e:
            self.db.rollback()
            return False, str(e)