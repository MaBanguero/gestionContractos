import os
import io
import pandas as pd
import requests
import urllib.parse
from datetime import datetime
from typing import Optional
from fastapi import FastAPI, Request, Depends, File, UploadFile, Cookie, HTTPException, status, Form, BackgroundTasks
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse, FileResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from mangum import Mangum
from jose import jwt, JWTError
from services.pdf_generator import GeneradorPDF
from fastapi.responses import Response

# --- IMPORTACIONES MODULARES ---
from core.database import engine, Base, get_db, SessionLocal
from models import db_models
from models.db_models import DBUsuario
from services.transactions import GestorTransacciones
from services.auth import verificar_password, obtener_password_hash, crear_token_acceso, SECRET_KEY, ALGORITHM

# Crear las tablas en la BD si no existen
db_models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="Control Financiero Modular")
templates = Jinja2Templates(directory="templates")


def enviar_webhook_pago(payload: dict):
    """
    Tarea en segundo plano (Background Task) para disparar la información a un API externa.
    Maneja sus propias excepciones para no tumbar la aplicación principal.
    """
    # TODO: Reemplaza esta URL y Token por los de tu API real
    URL_DESTINO = "https://api.tu-sistema-externo.com/v1/recepcion-pagos"
    HEADERS = {
        "Content-Type": "application/json",
        "Authorization": "Bearer TU_TOKEN_SECRETO_SI_APLICA"
    }

    try:
        # Timeout de 10 segundos para proteger el worker thread
        response = requests.post(URL_DESTINO, json=payload, headers=HEADERS, timeout=10)
        response.raise_for_status() # Lanza excepción si el status no es 2xx
        print(f"[WEBHOOK EXITO] Payload enviado a API externa. Status: {response.status_code}")
    except requests.exceptions.RequestException as e:
        print(f"[WEBHOOK ERROR] Fallo al comunicar con el API externa: {e}")

# ==========================================
# 1. SEGURIDAD Y AUTENTICACIÓN
# ==========================================

# Dependencia Guardián: Verifica si el usuario tiene sesión activa
def obtener_usuario_actual(token: str = Cookie(None), db: Session = Depends(get_db)):
    if not token:
        raise HTTPException(status_code=status.HTTP_303_SEE_OTHER, headers={"Location": "/login"})
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise HTTPException(status_code=status.HTTP_303_SEE_OTHER, headers={"Location": "/login"})
    except JWTError:
        raise HTTPException(status_code=status.HTTP_303_SEE_OTHER, headers={"Location": "/login"})

    user = db.query(DBUsuario).filter(DBUsuario.username == username).first()
    if user is None:
        raise HTTPException(status_code=status.HTTP_303_SEE_OTHER, headers={"Location": "/login"})
    return user


# Creador de Admin por defecto (Se ejecuta al arrancar el server)
@app.on_event("startup")
def crear_admin_inicial():
    db = SessionLocal()
    if not db.query(DBUsuario).first():
        admin = DBUsuario(username="admin", password_hash=obtener_password_hash("admin123"))
        db.add(admin)
        db.commit()
    db.close()


@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="login.html",
        context={"request": request}
    )


@app.post("/login")
async def procesar_login(request: Request, db: Session = Depends(get_db)):
    form = await request.form()
    username = form.get("username")
    password = form.get("password")

    user = db.query(DBUsuario).filter(DBUsuario.username == username).first()
    if not user or not verificar_password(password, user.password_hash):
        return templates.TemplateResponse(
            request=request,
            name="login.html",
            context={"request": request, "error": "Usuario o contraseña incorrectos"}
        )

    # Creamos la sesión y la guardamos en una cookie segura
    token = crear_token_acceso(data={"sub": user.username})
    response = RedirectResponse(url="/", status_code=303)  # Redirigimos al dashboard al entrar
    response.set_cookie(key="token", value=token, httponly=True)
    return response


@app.get("/logout")
def logout():
    response = RedirectResponse(url="/login", status_code=303)
    response.delete_cookie("token")
    return response


# ==========================================
# 2. RUTAS DE ADMINISTRACIÓN
# ==========================================

@app.get("/admin", response_class=HTMLResponse)
def panel_admin(request: Request, mensaje: str = None, error: str = None, db: Session = Depends(get_db),
                current_user: DBUsuario = Depends(obtener_usuario_actual)):
    usuarios = db.query(DBUsuario).all()
    return templates.TemplateResponse(
        request=request,
        name="admin.html",
        context={
            "request": request,
            "usuarios": usuarios,
            "usuario_actual": current_user,
            "mensaje": mensaje,
            "error": error
        }
    )


@app.post("/admin/usuarios")
async def crear_usuario(request: Request, db: Session = Depends(get_db),
                        current_user: DBUsuario = Depends(obtener_usuario_actual)):
    form = await request.form()
    username = form.get("username").strip()
    password = form.get("password").strip()

    if db.query(DBUsuario).filter(DBUsuario.username == username).first():
        return RedirectResponse(url="/admin?error=El nombre de usuario ya existe", status_code=303)

    nuevo_user = DBUsuario(username=username, password_hash=obtener_password_hash(password))
    db.add(nuevo_user)
    db.commit()
    return RedirectResponse(url="/admin?mensaje=Usuario creado con éxito", status_code=303)


@app.get("/admin/exportar_db")
def exportar_base_datos(current_user: DBUsuario = Depends(obtener_usuario_actual)):
    # Reemplaza "finanzas.db" con el nombre real de tu archivo SQLite si es diferente
    file_path = "finanzas.db"

    if os.path.exists(file_path):
        return FileResponse(path=file_path, filename="Backup_Finanzas_DB.db", media_type="application/octet-stream")
    return RedirectResponse(url="/admin?error=No se encontró el archivo de base de datos físico", status_code=303)


# ==========================================
# 3. RUTAS DE LECTURA (GET) PROTEGIDAS
# ==========================================

@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request, q: str = None, tipo_filtro: str = "todos", mensaje: str = None, error: str = None, db: Session = Depends(get_db), current_user: DBUsuario = Depends(obtener_usuario_actual)):
    tx = GestorTransacciones(db)
    resumen = tx.obtener_resumen_dashboard(busqueda=q, tipo_filtro=tipo_filtro, solo_inactivos=False)

    return templates.TemplateResponse(
        request=request, name="dashboard.html",
        context={"request": request, "contratos": resumen, "busqueda": q, "tipo_filtro": tipo_filtro, "solo_inactivos": False, "mensaje": mensaje, "error": error, "usuario_actual": current_user}
    )

@app.get("/contrato/crear", response_class=HTMLResponse)
def crear_contrato_vista(request: Request, db: Session = Depends(get_db),
                         current_user: DBUsuario = Depends(obtener_usuario_actual)):
    """ Muestra el formulario en blanco para un nuevo contrato """
    tx = GestorTransacciones(db)
    # INYECCIÓN DINÁMICA: Obtenemos los perfiles de la BD para popular el <select>
    perfiles_activos = tx.obtener_perfiles()

    return templates.TemplateResponse(
        request=request,
        name="formulario_contrato.html",
        context={
            "request": request,
            "contrato": None,
            "perfiles": perfiles_activos,
            "usuario_actual": current_user
        }
    )


@app.get("/contrato/editar_info/{numero_contrato:path}", response_class=HTMLResponse)
def editar_contrato_vista(request: Request, numero_contrato: str, db: Session = Depends(get_db),
                          current_user: DBUsuario = Depends(obtener_usuario_actual)):
    """ Muestra el formulario lleno con los datos existentes """
    tx = GestorTransacciones(db)
    detalle = tx.obtener_detalle_contrato(numero_contrato)

    if not detalle:
        return RedirectResponse(url="/?error=Contrato no encontrado", status_code=303)

    # INYECCIÓN DINÁMICA: Obtenemos los perfiles de la BD para popular el <select>
    perfiles_activos = tx.obtener_perfiles()

    return templates.TemplateResponse(
        request=request,
        name="formulario_contrato.html",
        context={
            "request": request,
            "contrato": detalle["contrato"],
            "perfiles": perfiles_activos,
            "usuario_actual": current_user
        }
    )

@app.post("/contrato/guardar")
async def registrar_contrato(request: Request, db: Session = Depends(get_db),
                             current_user: DBUsuario = Depends(obtener_usuario_actual)):
    form_data = dict(await request.form())

    # Limpiador de moneda (Quita puntos, comas y signos $)
    def limpiar_dinero(valor):
        if not valor: return 0.0
        val_str = str(valor).replace('$', '').replace(',', '').replace('.', '').strip()
        try:
            return float(val_str)
        except:
            return 0.0

    form_data['valor_total'] = limpiar_dinero(form_data.get('valor_total'))
    form_data['valor_final'] = limpiar_dinero(form_data.get('valor_final'))

    # Si el valor final viene en 0, asume el valor total inicial
    if form_data['valor_final'] == 0:
        form_data['valor_final'] = form_data['valor_total']

    tx = GestorTransacciones(db)
    exito, mensaje = tx.crear_o_actualizar_contrato(form_data)

    if exito:
        return RedirectResponse(url=f"/contrato/{form_data['numero_contrato']}?mensaje={mensaje}", status_code=303)
    return RedirectResponse(url=f"/?error={mensaje}", status_code=303)

@app.get("/contrato/{numero_contrato:path}", response_class=HTMLResponse)
def detalle_contrato(request: Request, numero_contrato: str, mensaje: str = None, error: str = None,
                     db: Session = Depends(get_db), current_user: DBUsuario = Depends(obtener_usuario_actual)):
    tx = GestorTransacciones(db)
    detalle = tx.obtener_detalle_contrato(numero_contrato)

    if not detalle:
        return RedirectResponse(url="/?error=Contrato no encontrado", status_code=303)

    return templates.TemplateResponse(
        request=request,
        name="detalle_contrato.html",
        context={
            "request": request,
            "contrato": detalle["contrato"],
            "pagos": detalle["pagos"],
            "total_pagado": detalle["total_pagado"],
            "saldo": detalle["saldo"],
            "acumulado_por_girar": detalle["acumulado_historico_pagado"],
            "valor_mensual_sugerido": detalle["valor_mensual_sugerido"],
            "porcentaje": detalle["porcentaje"],
            "proximo_pago": detalle["proximo_pago"],
            "mensaje": mensaje,
            "error": error,
            "usuario_actual": current_user
        }
    )


@app.get("/pago/editar/{pago_id}", response_class=HTMLResponse)
def editar_pago(request: Request, pago_id: int, db: Session = Depends(get_db),
                current_user: DBUsuario = Depends(obtener_usuario_actual)):
    tx = GestorTransacciones(db)
    pago = tx.obtener_pago_por_id(pago_id)
    if not pago:
        return RedirectResponse(url="/?error=Pago no encontrado", status_code=303)

    return templates.TemplateResponse(
        request=request,
        name="editar_pago.html",
        context={
            "request": request,
            "pago": pago,
            "usuario_actual": current_user
        }
    )


@app.get("/exportar_excel")
def exportar_excel(numero_contrato: Optional[str] = None, db: Session = Depends(get_db),
                   current_user: DBUsuario = Depends(obtener_usuario_actual)):
    tx = GestorTransacciones(db)
    df = tx.generar_excel_supervisiones(numero_contrato)

    stream = io.BytesIO()
    with pd.ExcelWriter(stream, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Supervisiones')
    stream.seek(0)

    if numero_contrato:
        nombre_limpio = numero_contrato.replace("/", "-")
        filename = f"Supervisiones_{nombre_limpio}.xlsx"
    else:
        filename = "Reporte_Supervisiones_Global.xlsx"

    headers = {'Content-Disposition': f'attachment; filename="{filename}"'}
    return StreamingResponse(stream, headers=headers,
                             media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')


# ==========================================
# 4. RUTAS DE ESCRITURA (POST) PROTEGIDAS
# ==========================================

@app.post("/contrato/nuevo")
async def registrar_contrato(request: Request, db: Session = Depends(get_db),
                             current_user: DBUsuario = Depends(obtener_usuario_actual)):
    form_data = dict(await request.form())
    form_data['valor_total'] = float(form_data.get('valor_total') or 0)
    form_data['valor_final'] = float(form_data.get('valor_final') or form_data['valor_total'])

    tx = GestorTransacciones(db)
    exito, mensaje = tx.crear_o_actualizar_contrato(form_data)

    if exito:
        return RedirectResponse(url=f"/contrato/{form_data['numero_contrato']}?mensaje={mensaje}", status_code=303)
    return RedirectResponse(url=f"/?error={mensaje}", status_code=303)


@app.post("/pago/nuevo_completo")
async def registrar_pago_completo(
        request: Request,
        background_tasks: BackgroundTasks,
        db: Session = Depends(get_db),
        current_user: DBUsuario = Depends(obtener_usuario_actual)
):
    form_data = await request.form()
    form_limpio = {}

    # 1. Copiar campos de metadatos normales (ignorando los arrays dinámicos)
    for key in form_data.keys():
        if not key.endswith("[]"):
            form_limpio[key] = form_data.get(key)

    # 2. Funciones de aplanamiento de datos
    def aggregate_names(entity):
        nombres = form_data.getlist(f"{entity}_nombre[]")
        otros = form_data.getlist(f"{entity}_nombre_otro[]")
        final_names = set()
        for i, nom in enumerate(nombres):
            val = otros[i] if nom == "OTRA" else nom
            if val and val.strip():
                final_names.add(val.strip().upper())
        return ", ".join(final_names)

    def aggregate_values(field):
        return sum(float(v) if v else 0.0 for v in form_data.getlist(f"{field}[]"))

    # 3. Aplanamiento Consolidado (Data Flattening)
    form_limpio["eps_nombre"] = aggregate_names("eps")
    form_limpio["eps_valor"] = aggregate_values("eps_valor")
    form_limpio["arl_nombre"] = aggregate_names("arl")
    form_limpio["arl_valor"] = aggregate_values("arl_valor")
    form_limpio["afp_nombre"] = aggregate_names("afp")
    form_limpio["afp_valor"] = aggregate_values("afp_valor")
    form_limpio["ccf_nombre"] = aggregate_names("ccf")
    form_limpio["ccf_valor"] = aggregate_values("ccf_valor")

    form_limpio["sena_valor"] = aggregate_values("sena_valor")
    form_limpio["icbf_valor"] = aggregate_values("icbf_valor")
    form_limpio["ibc"] = aggregate_values("ibc")
    form_limpio["valor_total_planilla"] = aggregate_values("valor_total_planilla")

    planillas = form_data.getlist("planilla_no[]")
    form_limpio["planilla_no"] = ", ".join(set(p.strip() for p in planillas if p.strip()))

    periodos = form_data.getlist("periodo_cotizado[]")
    form_limpio["periodo_cotizado"] = ", ".join(set(p.strip() for p in periodos if p.strip()))

    for c in ['numero_pago', 'valor_pagado', 'valor_a_pagar']:
        if c in form_limpio:
            form_limpio[c] = float(form_limpio[c] or 0)

    if 'numero_contrato' in form_limpio:
        form_limpio['contrato_id'] = form_limpio.pop('numero_contrato')

    # 4. Transacción en Base de Datos
    tx = GestorTransacciones(db)
    exito, msg = tx.registrar_pago_supervision(form_limpio)

    # 5. DISPARADOR DEL WEBHOOK (EVENT-DRIVEN ARCHITECTURE)
    if exito:
        contrato_id = form_limpio.get('contrato_id')
        contrato_db = db.query(db_models.DBContrato).filter(db_models.DBContrato.numero_contrato == contrato_id).first()

        if contrato_db:
            historial_pagos = []

            # Ordenamos los pagos para que el sistema externo los reciba cronológicamente
            pagos_ordenados = sorted(contrato_db.pagos, key=lambda x: x.numero_pago)

            for p in pagos_ordenados:
                historial_pagos.append({
                    "id_interno": p.id,
                    "numero_pago": p.numero_pago,
                    "tipo_informe": p.tipo_informe or "N/A",
                    "periodo_desde": p.periodo_desde,
                    "periodo_hasta": p.periodo_hasta,
                    "valor_a_pagar": float(p.valor_a_pagar or 0),
                    "valor_pagado_progresivo": float(p.valor_pagado or 0),
                    "planilla_no": p.planilla_no or "N/A",
                    "periodo_cotizado": p.periodo_cotizado or "N/A",
                    "ibc": float(p.ibc or 0),
                    "seguridad_social": {
                        "eps": {"nombre": p.eps_nombre or "N/A", "valor": float(p.eps_valor or 0)},
                        "arl": {"nombre": p.arl_nombre or "N/A", "valor": float(p.arl_valor or 0)},
                        "afp": {"nombre": p.afp_nombre or "N/A", "valor": float(p.afp_valor or 0)},
                        "ccf": {"nombre": p.ccf_nombre or "N/A", "valor": float(p.ccf_valor or 0)},
                        "sena": float(p.sena_valor or 0),
                        "icbf": float(p.icbf_valor or 0),
                        "total_planilla": float(p.valor_total_planilla or 0)
                    },
                    "fecha_registro_sistema": p.fecha_registro.isoformat() if p.fecha_registro else None,
                    "actividades": p.actividades or "N/A",
                    "observaciones": p.observaciones or "N/A"
                })

            # Construimos el Payload Masivo (State Snapshot)
            payload_masivo = {
                "metadata": {
                    "evento": "PAGO_REGISTRADO_ACTUALIZADO",
                    "fecha_disparo": datetime.utcnow().isoformat(),
                    "usuario_auditor": current_user.username,
                    "total_pagos_registrados": len(historial_pagos)
                },
                "contratista": {
                    "identificacion": contrato_db.contratista_id,
                    "nombre": contrato_db.contratista.nombre if contrato_db.contratista else "N/A",
                    "telefono": contrato_db.contratista.telefono if contrato_db.contratista else "N/A",
                    "direccion": contrato_db.contratista.direccion if contrato_db.contratista else "N/A",
                    "tipo_persona": contrato_db.contratista.tipo_persona if contrato_db.contratista else "NATURAL"
                },
                "contrato": {
                    "numero_contrato": contrato_db.numero_contrato,
                    "estado_actual": contrato_db.estado or "ACTIVO",
                    "perfil": contrato_db.perfil or "N/A",
                    "resolucion": contrato_db.resolucion or "N/A",
                    "tipologia": contrato_db.tipologia or "N/A",
                    "cdp": contrato_db.cdp or "N/A",
                    "crp": contrato_db.crp or "N/A",
                    "imputacion": contrato_db.imputacion or "N/A",
                    "valor_total": float(contrato_db.valor_total or 0),
                    "valor_final": float(contrato_db.valor_final or 0),
                    "fecha_inicio": contrato_db.fecha_inicio or "N/A",
                    "fecha_terminacion": contrato_db.fecha_terminacion or "N/A",
                },
                "pago_actual_inmediato": form_limpio,
                "historial_completo_pagos": historial_pagos
            }

            # Encolamos la tarea para que el usuario no tenga que esperar el response de la API externa
            print(payload_masivo)
            background_tasks.add_task(enviar_webhook_pago, payload_masivo)

    # 6. Redirección al usuario (Cierre de ciclo)
    contrato_encode = urllib.parse.quote(form_limpio.get('contrato_id', ''), safe='')
    estado = "mensaje" if exito else "error"
    return RedirectResponse(url=f"/contrato/{contrato_encode}?{estado}={msg}", status_code=303)


@app.post("/importar_csv")
async def importar_csv(archivo: UploadFile = File(...), db: Session = Depends(get_db),
                       current_user: DBUsuario = Depends(obtener_usuario_actual)):
    content = await archivo.read()
    try:
        decoded_content = content.decode('utf-8')
    except:
        decoded_content = content.decode('latin-1')

    tx = GestorTransacciones(db)
    exito, msg = tx.importar_datos_csv(decoded_content)

    estado = "mensaje" if exito else "error"
    return RedirectResponse(url=f"/?{estado}={msg}", status_code=303)


@app.post("/pago/actualizar/{pago_id}")
async def procesar_actualizacion(request: Request, pago_id: int, db: Session = Depends(get_db),
                                 current_user: DBUsuario = Depends(obtener_usuario_actual)):
    form_data = await request.form()
    form_limpio = {}

    for key in form_data.keys():
        if not key.endswith("[]"):
            form_limpio[key] = form_data.get(key)

    def aggregate_names(entity):
        nombres = form_data.getlist(f"{entity}_nombre[]")
        otros = form_data.getlist(f"{entity}_nombre_otro[]")
        final_names = set()
        for i, nom in enumerate(nombres):
            val = otros[i] if nom == "OTRA" else nom
            if val and val.strip():
                final_names.add(val.strip().upper())
        return ", ".join(final_names)

    def aggregate_values(field):
        return sum(float(v) if v else 0.0 for v in form_data.getlist(f"{field}[]"))

    form_limpio["eps_nombre"] = aggregate_names("eps")
    form_limpio["eps_valor"] = aggregate_values("eps_valor")
    form_limpio["arl_nombre"] = aggregate_names("arl")
    form_limpio["arl_valor"] = aggregate_values("arl_valor")
    form_limpio["afp_nombre"] = aggregate_names("afp")
    form_limpio["afp_valor"] = aggregate_values("afp_valor")
    form_limpio["ccf_nombre"] = aggregate_names("ccf")
    form_limpio["ccf_valor"] = aggregate_values("ccf_valor")
    form_limpio["sena_valor"] = aggregate_values("sena_valor")
    form_limpio["icbf_valor"] = aggregate_values("icbf_valor")
    form_limpio["ibc"] = aggregate_values("ibc")
    form_limpio["valor_total_planilla"] = aggregate_values("valor_total_planilla")

    planillas = form_data.getlist("planilla_no[]")
    form_limpio["planilla_no"] = ", ".join(set(p.strip() for p in planillas if p.strip()))

    periodos = form_data.getlist("periodo_cotizado[]")
    form_limpio["periodo_cotizado"] = ", ".join(set(p.strip() for p in periodos if p.strip()))

    for c in ['valor_pagado', 'valor_a_pagar']:
        if c in form_limpio:
            form_limpio[c] = float(form_limpio[c] or 0)

    tx = GestorTransacciones(db)
    exito, msg = tx.actualizar_pago_existente(pago_id, form_limpio)

    pago = tx.obtener_pago_por_id(pago_id)
    import urllib.parse
    contrato_encode = urllib.parse.quote(pago.contrato_id, safe='')
    estado = "mensaje" if exito else "error"
    return RedirectResponse(url=f"/contrato/{contrato_encode}?{estado}={msg}", status_code=303)


@app.post("/pago/eliminar/{pago_id}")
async def procesar_borrado_pago(pago_id: int, db: Session = Depends(get_db),
                                current_user: DBUsuario = Depends(obtener_usuario_actual)):
    tx = GestorTransacciones(db)
    pago = tx.obtener_pago_por_id(pago_id)
    if not pago:
        return RedirectResponse(url="/?error=Pago no encontrado", status_code=303)

    id_contrato = pago.contrato_id
    exito, msg = tx.eliminar_pago(pago_id)

    estado = "mensaje" if exito else "error"
    return RedirectResponse(url=f"/contrato/{id_contrato}?{estado}={msg}", status_code=303)


@app.get("/pago/pdf/{pago_id}")
def descargar_pdf_pago(pago_id: int, db: Session = Depends(get_db), current_user: DBUsuario = Depends(obtener_usuario_actual)):
    generador = GeneradorPDF(db, templates)
    # Sin await aquí
    pdf_bytes, nombre_archivo = generador.generar_pdf_pago_unico(pago_id)
    if not pdf_bytes:
        return RedirectResponse(url="/?error=No se pudo generar el PDF", status_code=303)
    return Response(content=pdf_bytes, media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="{nombre_archivo}"'})

@app.get("/contratista/{identificacion}/pdfs")
def descargar_pdfs_contratista(identificacion: str, db: Session = Depends(get_db), current_user: DBUsuario = Depends(obtener_usuario_actual)):
    generador = GeneradorPDF(db, templates)
    # Sin await aquí
    zip_buffer = generador.generar_zip_contratista(identificacion)
    return StreamingResponse(zip_buffer, media_type="application/zip", headers={"Content-Disposition": f'attachment; filename="Reportes_{identificacion}.zip"'})

@app.get("/perfiles", response_class=HTMLResponse)
async def vista_perfiles(request: Request, db: Session = Depends(get_db)):
    gestor = GestorTransacciones(db)
    perfiles = gestor.obtener_perfiles()
    return templates.TemplateResponse(
        request=request,
        name="gestion_perfiles.html",
        context={"request": request, "perfiles": perfiles}
    )

@app.post("/perfiles/crear")
async def crear_perfil(
    nombre: str = Form(...),
    descripcion: str = Form(""),
    honorario_referencia: float = Form(0.0),
    db: Session = Depends(get_db),
    current_user: DBUsuario = Depends(obtener_usuario_actual)
):
    """Crea un nuevo perfil con su respectivo honorario de referencia."""
    tx = GestorTransacciones(db)
    exito, msg = tx.crear_perfil(nombre, descripcion, honorario_referencia)
    estado = "mensaje" if exito else "error"
    return RedirectResponse(url=f"/perfiles?{estado}={msg}", status_code=303)

@app.get("/perfiles/{perfil_id}", response_class=HTMLResponse)
async def detalle_perfil(request: Request, perfil_id: int, db: Session = Depends(get_db)):
    gestor = GestorTransacciones(db)
    perfil = gestor.obtener_perfil(perfil_id)
    # Ordenar actividades para la vista
    actividades = sorted(perfil.actividades, key=lambda x: x.orden) if perfil else []
    return templates.TemplateResponse(
        request=request,
        name="detalle_perfil.html",
        context={"request": request, "perfil": perfil, "actividades": actividades}
    )

@app.post("/perfiles/{perfil_id}/editar")
async def actualizar_perfil_endpoint(
    perfil_id: int,
    nombre: str = Form(...),
    descripcion: str = Form(""),
    honorario_referencia: float = Form(0.0),
    db: Session = Depends(get_db),
    current_user: DBUsuario = Depends(obtener_usuario_actual)
):
    """Procesa la actualización de los datos maestro del perfil."""
    tx = GestorTransacciones(db)
    exito, msg = tx.editar_perfil(perfil_id, nombre, descripcion, honorario_referencia)
    estado = "mensaje" if exito else "error"
    return RedirectResponse(url=f"/perfiles/{perfil_id}?{estado}={msg}", status_code=303)


@app.post("/perfiles/{perfil_id}/eliminar")
async def borrar_perfil_endpoint(
    perfil_id: int,
    db: Session = Depends(get_db),
    current_user: DBUsuario = Depends(obtener_usuario_actual)
):
    """Procesa la eliminación absoluta de un perfil y redirige al dashboard central."""
    tx = GestorTransacciones(db)
    exito, msg = tx.eliminar_perfil(perfil_id)
    estado = "mensaje" if exito else "error"
    return RedirectResponse(url=f"/perfiles?{estado}={msg}", status_code=303)

@app.post("/perfiles/{perfil_id}/actividades")
async def nueva_actividad(perfil_id: int, descripcion: str = Form(...), orden: int = Form(0), db: Session = Depends(get_db)):
    gestor = GestorTransacciones(db)
    gestor.agregar_actividad(perfil_id, descripcion, orden)
    return RedirectResponse(url=f"/perfiles/{perfil_id}", status_code=303)

@app.post("/actividades/{actividad_id}/eliminar")
async def borrar_actividad(actividad_id: int, perfil_id: int = Form(...), db: Session = Depends(get_db)):
    gestor = GestorTransacciones(db)
    gestor.eliminar_actividad(actividad_id)
    return RedirectResponse(url=f"/perfiles/{perfil_id}", status_code=303)


@app.get("/actividades/{actividad_id}/editar", response_class=HTMLResponse)
async def vista_editar_actividad(request: Request, actividad_id: int, db: Session = Depends(get_db),
                                 current_user: DBUsuario = Depends(obtener_usuario_actual)):
    """Renderiza el entorno de edición para una obligación específica."""
    tx = GestorTransacciones(db)
    actividad = tx.obtener_actividad(actividad_id)

    if not actividad:
        return RedirectResponse(url="/perfiles?error=Actividad no encontrada", status_code=303)

    return templates.TemplateResponse(
        request=request,
        name="editar_actividad.html",
        context={"request": request, "actividad": actividad, "usuario_actual": current_user}
    )

@app.post("/actividades/{actividad_id}/editar")
async def actualizar_actividad(
        actividad_id: int,
        perfil_id: int = Form(...),
        descripcion: str = Form(...),
        orden: int = Form(0),
        db: Session = Depends(get_db),
        current_user: DBUsuario = Depends(obtener_usuario_actual)
):
    """Procesa la mutación de la actividad en la base de datos."""
    tx = GestorTransacciones(db)
    exito, msg = tx.editar_actividad(actividad_id, descripcion, orden)
    estado = "mensaje" if exito else "error"
    # Retorna al detalle del perfil para ver los cambios reflejados
    return RedirectResponse(url=f"/perfiles/{perfil_id}?{estado}={msg}", status_code=303)


@app.get("/contratos_pasados", response_class=HTMLResponse)
def contratos_archivados(request: Request, q: str = None, tipo_filtro: str = "todos", mensaje: str = None, error: str = None, db: Session = Depends(get_db), current_user: DBUsuario = Depends(obtener_usuario_actual)):
    tx = GestorTransacciones(db)
    resumen = tx.obtener_resumen_dashboard(busqueda=q, tipo_filtro=tipo_filtro, solo_inactivos=True)

    return templates.TemplateResponse(
        request=request, name="dashboard.html",
        context={"request": request, "contratos": resumen, "busqueda": q, "tipo_filtro": tipo_filtro, "solo_inactivos": True, "mensaje": mensaje, "error": error, "usuario_actual": current_user}
    )

@app.get("/api/contratistas")
async def api_buscar_contratistas(q: str = "", db: Session = Depends(get_db)):
    if len(q) < 2:
        return JSONResponse(content=[])
    tx = GestorTransacciones(db)
    resultados = tx.buscar_contratistas(q)
    return JSONResponse(content=[{
        "identificacion": c.identificacion,
        "nombre": c.nombre or "",
        "expedida_en": c.expedida_en or "",
        "telefono": c.telefono or "",
        "direccion": c.direccion or "",
        "tipo_persona": c.tipo_persona or "NATURAL",
    } for c in resultados])


@app.get("/contratista/{identificacion}/editar", response_class=HTMLResponse)
def editar_contratista_vista(request: Request, identificacion: str, mensaje: str = None, error: str = None,
                              db: Session = Depends(get_db), current_user: DBUsuario = Depends(obtener_usuario_actual)):
    tx = GestorTransacciones(db)
    contratista = tx.obtener_contratista(identificacion)
    if not contratista:
        return RedirectResponse(url="/?error=Contratista no encontrado", status_code=303)
    return templates.TemplateResponse(
        request=request,
        name="editar_contratista.html",
        context={"request": request, "contratista": contratista, "mensaje": mensaje, "error": error, "usuario_actual": current_user}
    )


@app.post("/contratista/{identificacion}/editar")
async def actualizar_contratista_endpoint(request: Request, identificacion: str, db: Session = Depends(get_db),
                                          current_user: DBUsuario = Depends(obtener_usuario_actual)):
    form_data = dict(await request.form())
    tx = GestorTransacciones(db)
    exito, msg = tx.actualizar_contratista(identificacion, form_data)
    id_encode = urllib.parse.quote(identificacion, safe='')
    estado = "mensaje" if exito else "error"
    return RedirectResponse(url=f"/contratista/{id_encode}/editar?{estado}={msg}", status_code=303)


@app.get("/api/buscar_contratos")
async def api_buscar_contratos(q: str = "", tipo_filtro: str = "todos", solo_inactivos: str = "false", db: Session = Depends(get_db)):
    tx = GestorTransacciones(db)
    es_archivo = solo_inactivos == "true"
    resultados = tx.obtener_resumen_dashboard(busqueda=q, tipo_filtro=tipo_filtro, solo_inactivos=es_archivo)
    return JSONResponse(content=resultados)


@app.post("/contrato/{numero_contrato:path}/estado")
async def cambiar_estado_endpoint(numero_contrato: str, estado: str = Form(...), db: Session = Depends(get_db),
                                  current_user: DBUsuario = Depends(obtener_usuario_actual)):
    """Endpoint para archivar o restaurar un contrato."""
    tx = GestorTransacciones(db)
    exito, msg = tx.cambiar_estado_contrato(numero_contrato, estado)
    estado_url = "mensaje" if exito else "error"

    # Aseguramos que la redirección maneje correctamente los espacios y caracteres especiales
    import urllib.parse
    contrato_encode = urllib.parse.quote(numero_contrato, safe='')

    return RedirectResponse(url=f"/contrato/{contrato_encode}?{estado_url}={msg}", status_code=303)

@app.get("/plantillas_observaciones", response_class=HTMLResponse)
async def vista_plantillas(request: Request, db: Session = Depends(get_db), current_user: DBUsuario = Depends(obtener_usuario_actual)):
    tx = GestorTransacciones(db)
    plantillas = tx.obtener_plantillas_observaciones()
    return templates.TemplateResponse(
        request=request, name="gestion_plantillas.html",
        context={"request": request, "plantillas": plantillas, "usuario_actual": current_user, "mensaje": request.query_params.get("mensaje"), "error": request.query_params.get("error")}
    )

@app.post("/plantillas_observaciones/crear")
async def crear_plantilla(titulo: str = Form(...), contenido: str = Form(...), db: Session = Depends(get_db), current_user: DBUsuario = Depends(obtener_usuario_actual)):
    tx = GestorTransacciones(db)
    exito, msg = tx.crear_plantilla_observacion(titulo, contenido)
    estado = "mensaje" if exito else "error"
    return RedirectResponse(url=f"/plantillas_observaciones?{estado}={msg}", status_code=303)

@app.post("/plantillas_observaciones/{plantilla_id}/editar")
async def editar_plantilla(plantilla_id: int, titulo: str = Form(...), contenido: str = Form(...), db: Session = Depends(get_db), current_user: DBUsuario = Depends(obtener_usuario_actual)):
    tx = GestorTransacciones(db)
    exito, msg = tx.actualizar_plantilla_observacion(plantilla_id, titulo, contenido)
    estado = "mensaje" if exito else "error"
    return RedirectResponse(url=f"/plantillas_observaciones?{estado}={msg}", status_code=303)

@app.post("/plantillas_observaciones/{plantilla_id}/eliminar")
async def eliminar_plantilla(plantilla_id: int, db: Session = Depends(get_db), current_user: DBUsuario = Depends(obtener_usuario_actual)):
    tx = GestorTransacciones(db)
    exito, msg = tx.eliminar_plantilla_observacion(plantilla_id)
    estado = "mensaje" if exito else "error"
    return RedirectResponse(url=f"/plantillas_observaciones?{estado}={msg}", status_code=303)

@app.get("/api/plantillas_observaciones")
async def api_obtener_plantillas(db: Session = Depends(get_db)):
    """Endpoint que consume el frontend (AJAX) para inyectar el desplegable de observaciones."""
    tx = GestorTransacciones(db)
    plantillas = tx.obtener_plantillas_observaciones()
    return JSONResponse(content=[{"id": p.id, "titulo": p.titulo, "contenido": p.contenido} for p in plantillas])

# Adaptador AWS
handler = Mangum(app)