import os
import sys

# Asegurar que los módulos de la aplicación sean reconocidos
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from core.database import SessionLocal, engine
# IMPORTANTE: Se agrega DBPlantillaObservacion
from models.db_models import Base, DBPerfil, DBActividadPerfil, DBContrato, DBPlantillaObservacion
from services.pdf_generator import ACTIVIDADES_POR_PERFIL, HONORARIOS_POR_PERFIL

# ==========================================
# CATÁLOGO ESTÁTICO DE PLANTILLAS LEGALES
# ==========================================
PLANTILLAS_OBSERVACIONES = [
    {
        "titulo": "CUMPLIMIENTO TOTAL (SIN DESCUENTO)",
        "contenido": "Una vez verificado el informe de actividades, los soportes allegados y demás evidencias presentadas por el CONTRATISTA, se constata el cumplimiento de las obligaciones contractuales correspondientes al periodo evaluado, conforme a lo establecido en el contrato. En consecuencia, desde la supervisión se conceptúa favorablemente el cumplimiento de las actividades desarrolladas y se autoriza el trámite de pago de la cuenta de cobro presentada, por encontrarse debidamente soportada. No obstante, se recomienda al CONTRATISTA mantener vigente su afiliación a las administradoras del Sistema General de Seguridad Social Integral, así como continuar efectuando de manera oportuna los aportes correspondientes, en cumplimiento de la normativa vigente aplicable y de las obligaciones contractuales asumidas, mínimo, mientras se encuentre vigente el contrato."
    },
    {
        "titulo": "CUMPLIMIENTO PARCIAL (CON DESCUENTO)",
        "contenido": "Verificado lo informes de actividades, los soportes allegados y demás evidencias presentadas por el CONTRATISTA, se evidencia un cumplimiento parcial de las obligaciones contractuales correspondientes al periodo evaluado, conforme a lo establecido en el contrato y en el plan de actividades aprobado. Se deja constancia de que no se ejecutó la totalidad de las actividades previstas, situación que se encuentra debidamente soportada en la verificación realizada por la supervisión. En consecuencia, y en aplicación del principio de pago contra prestación efectivamente ejecutada, así como de lo pactado en el contrato, la supervisión determina el reconocimiento y pago únicamente de las actividades efectivamente desarrolladas y soportadas, procediendo al ajuste del valor de la cuenta de cobro en proporción a dicho cumplimiento. Por lo anterior, se autoriza el trámite de pago por el valor ajustado, conforme a la verificación efectuada. Finalmente, se recomienda al CONTRATISTA mantener vigente su afiliación al Sistema General de Seguridad Social Integral y efectuar oportunamente los aportes correspondientes, en cumplimiento de la normativa vigente y de las obligaciones contractuales asumidas."
    },
    {
        "titulo": "RECUPERACION DE DESCUENTO",
        "contenido": "Verificado el informe de actividades, los soportes allegados y demás evidencias presentadas por el CONTRATISTA, se evidencia que durante el periodo evaluado se ejecutaron actividades adicionales y/o se subsanaron aquellas que dieron lugar a la aplicación de un descuento en periodos anteriores, dentro del mismo término de ejecución contractual. En ese sentido, la supervisión constata que las actividades previamente no reconocidas fueron efectivamente desarrolladas y debidamente soportadas, cumpliendo con las condiciones técnicas y contractuales exigidas. En consecuencia, y en aplicación del principio de reconocimiento de la prestación efectivamente ejecutada, se autoriza la recuperación del valor descontado, en proporción a las actividades verificadas, procediendo su inclusión en el trámite de pago correspondiente al presente periodo. Lo anterior se realiza sin que ello implique modificación de las condiciones contractuales, sino en garantía del equilibrio contractual y del pago justo por las actividades efectivamente ejecutadas y acreditadas."
    }
]


def inicializar_base_de_datos():
    """
    Script de migración atómica:
    1. Verifica la existencia de las tablas.
    2. Itera sobre los diccionarios estáticos de perfiles y honorarios.
    3. Inyecta los datos en la base de datos relacional evitando duplicados.
    4. Actualiza masivamente los contratos existentes asignándoles la Resolución 1010.
    5. Inyecta el catálogo inicial de Plantillas de Observaciones.
    """
    print(">>> Iniciando migración de datos (Seed Process) ...")

    # Asegura que las nuevas tablas (incluyendo plantillas_observaciones) existan
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    try:
        perfiles_creados = 0
        actividades_creadas = 0
        plantillas_creadas = 0

        # --- 1. INYECCIÓN DE PERFILES Y OBLIGACIONES ---
        for nombre_perfil, lista_actividades in ACTIVIDADES_POR_PERFIL.items():
            perfil_limpio = nombre_perfil.strip().upper()

            # Buscar si el perfil ya existe en la BD
            perfil_db = db.query(DBPerfil).filter(DBPerfil.nombre == perfil_limpio).first()

            if not perfil_db:
                # Recuperar el honorario base del diccionario (si no existe, asigna 0.0)
                honorario_base = float(HONORARIOS_POR_PERFIL.get(perfil_limpio, 0.0))

                # Insertar nuevo perfil incluyendo su honorario de referencia
                perfil_db = DBPerfil(
                    nombre=perfil_limpio,
                    descripcion="Migrado desde configuración estática.",
                    honorario_referencia=honorario_base
                )
                db.add(perfil_db)
                db.flush()  # Vacía el registro para obtener el ID asignado por la BD
                perfiles_creados += 1

                # Inyectar las actividades (ordenadas según la lista original)
                for index, descripcion_actividad in enumerate(lista_actividades, start=1):
                    actividad_db = DBActividadPerfil(
                        perfil_id=perfil_db.id,
                        descripcion=descripcion_actividad.strip(),
                        orden=index
                    )
                    db.add(actividad_db)
                    actividades_creadas += 1
            else:
                print(f"[-] El perfil {perfil_limpio} ya existe. Omitiendo para evitar duplicidad.")

        # --- 2. ACTUALIZACIÓN MASIVA DE CONTRATOS (RESOLUCIÓN 1010) ---
        # Actualiza todos los contratos donde la resolución sea NULL o esté vacía
        contratos_actualizados = db.query(DBContrato).filter(
            (DBContrato.resolucion == None) | (DBContrato.resolucion == "")
        ).update({"resolucion": "1010"}, synchronize_session=False)

        # --- 3. INYECCIÓN DE PLANTILLAS DE OBSERVACIONES ---
        for p_data in PLANTILLAS_OBSERVACIONES:
            titulo_limpio = p_data["titulo"].strip().upper()
            plantilla_db = db.query(DBPlantillaObservacion).filter(
                DBPlantillaObservacion.titulo == titulo_limpio).first()

            if not plantilla_db:
                nueva_plantilla = DBPlantillaObservacion(
                    titulo=titulo_limpio,
                    contenido=p_data["contenido"].strip()
                )
                db.add(nueva_plantilla)
                plantillas_creadas += 1
            else:
                print(f"[-] La plantilla '{titulo_limpio}' ya existe. Omitiendo para evitar duplicidad.")

        db.commit()
        print(f"\n>>> Migración finalizada con éxito.")
        print(f">>> Perfiles creados: {perfiles_creados}")
        print(f">>> Obligaciones insertadas: {actividades_creadas}")
        print(f">>> Contratos actualizados con Resolución 1010: {contratos_actualizados}")
        print(f">>> Plantillas de Observaciones creadas: {plantillas_creadas}")

    except Exception as e:
        db.rollback()
        print(f"\n!!! Error Crítico durante la migración: {str(e)}")
    finally:
        db.close()


if __name__ == "__main__":
    inicializar_base_de_datos()