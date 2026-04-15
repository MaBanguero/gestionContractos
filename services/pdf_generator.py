import os
import io
import base64
import zipfile
import re
from datetime import datetime
from sqlalchemy.orm import Session
from fastapi.templating import Jinja2Templates
from playwright.async_api import async_playwright
from models.db_models import DBPago, DBContratista

# --- DICCIONARIO DE ACTIVIDADES ORIGINAL ---
ACTIVIDADES_POR_PERFIL = {
    "MEDICINA": [
        "Realizar la identificación integral del riesgo individual, familiar y comunitario de la población adscrita al microterritorio asignado, considerando enfoques del PICP.",
        "Ejecutar las atenciones individuales de promoción y mantenimiento de la salud, conforme a la Resolución 3280 de 2018 y lineamientos técnicos.",
        "Aplicar las guías de práctica clínica, protocolos institucionales y lineamientos técnicos definidos por la E.S.E. NORTE 3.",
        "Realizar acciones de inducción a la demanda de servicios de salud, priorizando eventos de salud pública.",
        "Identificar, notificar y gestionar oportunamente los eventos de interés en salud pública.",
        "Realizar la canalización oportuna de las personas a los servicios de salud del nivel primario o red de prestación.",
        "Hacer seguimiento efectivo al acceso y continuidad de las atenciones en salud dentro de la red.",
        "Promover espacios de concertación y mediación intercultural cuando aplique.",
        "Promover y gestionar la articulación intersectorial y transectorial de los servicios de salud, sociales y ambientales.",
        "Socializar con las comunidades atendidas los resultados de la caracterización familiar y del entorno.",
        "Realizar la sistematización, registro y reporte de la información en los sistemas del Ministerio de Salud (PICP, canalización, seguimiento).",
        "Identificar potencialidades, factores protectores y riesgos en los entornos para priorizar intervenciones.",
        "Concertar y programar acciones sectoriales e intersectoriales enfocadas en la ejecución del PICP.",
        "Participar en acciones de trabajo colaborativo, capacitación, cuidado al cuidador y seguimiento a la gestión del equipo.",
        "Implementar las intervenciones colectivas concertadas en el PICP que correspondan al perfil médico.",
        "Gestionar la garantía de las atenciones individuales en promoción, mantenimiento, detección temprana, diagnóstico y tratamiento.",
        "Activar y gestionar los mecanismos de referencia y contrarreferencia.",
        "Hacer uso adecuado de las Tecnologías de la Información y las Comunicaciones (TIC).",
        "Diligenciar diaria, completa y oportunamente los Registros Individuales de Prestación de Servicios de Salud (RIPS) con códigos CIE-10.",
        "Diligenciar de forma objetiva, clara y pertinente la historia clínica electrónica.",
        "Cuando aplique, diligenciar la historia clínica física, garantizando legibilidad y completitud.",
        "Educar a pacientes y familias sobre tratamientos, autocuidado y signos de alarma.",
        "Hacer uso adecuado y responsable de los equipos, medicamentos, dispositivos e insumos.",
        "Cumplir con las atenciones definidas para las familias beneficiarias según programación mensual.",
        "Cumplir las normas de bioseguridad y seguridad del paciente.",
        "Atender las orientaciones técnicas y de coordinación operativa del Coordinador EBS.",
        "Cumplir con el plan de capacitaciones definido por la E.S.E. NORTE 3.",
        "Registrar y validar las valoraciones médicas integrales acompañadas de educación en salud.",
        "Contribuir al cumplimiento de las metas del programa con referencia al 100% de la población caracterizada.",
        "Realizar un total de quinientas cuarenta (540) atenciones individuales mensuales, en el marco de la Promoción y Mantenimiento de la Salud, de conformidad con la Resolución 3280 de 2018, los lineamientos técnicos vigentes del Ministerio de Salud y Protección Social y la planeación institucional de la Empresa Social del Estado NORTE 3 - E.S.E., distribuidas así:<br><br><table style='width:100%; border-collapse: collapse; font-size: 9px; margin-top: 5px;'><tr><th style='border: 1px solid #000; padding: 4px; background-color: #f2f2f2;'>GRUPO ETAREO</th><th style='border: 1px solid #000; padding: 4px; background-color: #f2f2f2;'>DESCRIPCIÓN DE LA ATENCIÓN</th><th style='border: 1px solid #000; padding: 4px; background-color: #f2f2f2; text-align: center;'>NO. DE ATENCIONES</th></tr><tr><td style='border: 1px solid #000; padding: 4px;'>ADOLESCENCIA</td><td style='border: 1px solid #000; padding: 4px;'>ATENCIÓN EN SALUD POR MEDICINA GENERAL, ASESORÍA EN ANTICONCEPCIÓN</td><td style='border: 1px solid #000; padding: 4px; text-align: center;'>15</td></tr><tr><td style='border: 1px solid #000; padding: 4px;'>JUVENTUD</td><td style='border: 1px solid #000; padding: 4px;'>ATENCIÓN EN SALUD POR MEDICINA GENERAL, ASESORÍA EN ANTICONCEPCIÓN</td><td style='border: 1px solid #000; padding: 4px; text-align: center;'>22</td></tr><tr><td style='border: 1px solid #000; padding: 4px;'>ADULTEZ</td><td style='border: 1px solid #000; padding: 4px;'>ATENCIÓN EN SALUD POR MEDICINA GENERAL, ASESORÍA EN ANTICONCEPCIÓN</td><td style='border: 1px solid #000; padding: 4px; text-align: center;'>18</td></tr><tr><td style='border: 1px solid #000; padding: 4px;'>ADULTEZ</td><td style='border: 1px solid #000; padding: 4px;'>TAMIZAJE PARA CÁNCER DE PRÓSTATA (PSA)</td><td style='border: 1px solid #000; padding: 4px; text-align: center;'>11</td></tr><tr><td style='border: 1px solid #000; padding: 4px;'>ADULTEZ</td><td style='border: 1px solid #000; padding: 4px;'>TAMIZAJE PARA CÁNCER DE PRÓSTATA (TACTO RECTAL)</td><td style='border: 1px solid #000; padding: 4px; text-align: center;'>11</td></tr><tr><td style='border: 1px solid #000; padding: 4px;'>ADULTEZ</td><td style='border: 1px solid #000; padding: 4px;'>TAMIZAJE PARA CÁNCER DE COLON (SANGRE OCULTA EN MATERIA FECAL POR INMUNOQUÍMICA)</td><td style='border: 1px solid #000; padding: 4px; text-align: center;'>7</td></tr><tr><td style='border: 1px solid #000; padding: 4px;'>ADULTEZ</td><td style='border: 1px solid #000; padding: 4px;'>ATENCIÓN PRECONCEPCIONAL</td><td style='border: 1px solid #000; padding: 4px; text-align: center;'>41</td></tr><tr><td style='border: 1px solid #000; padding: 4px;'>ADULTEZ</td><td style='border: 1px solid #000; padding: 4px;'>TAMIZAJE PARA CÁNCER DE MAMA (VALORACIÓN CLÍNICA DE LA MAMA)</td><td style='border: 1px solid #000; padding: 4px; text-align: center;'>84</td></tr><tr><td style='border: 1px solid #000; padding: 4px;'>VEJEZ</td><td style='border: 1px solid #000; padding: 4px;'>ATENCIÓN EN SALUD POR MEDICINA GENERAL, ASESORIA EN ANTICONCEPCIÓN</td><td style='border: 1px solid #000; padding: 4px; text-align: center;'>58</td></tr><tr><td style='border: 1px solid #000; padding: 4px;'>VEJEZ</td><td style='border: 1px solid #000; padding: 4px;'>TAMIZAJE PARA CÁNCER DE PRÓSTATA (PSA)</td><td style='border: 1px solid #000; padding: 4px; text-align: center;'>11</td></tr><tr><td style='border: 1px solid #000; padding: 4px;'>VEJEZ</td><td style='border: 1px solid #000; padding: 4px;'>TAMIZAJE PARA CÁNCER DE PRÓSTATA (TACTO RECTAL)</td><td style='border: 1px solid #000; padding: 4px; text-align: center;'>11</td></tr><tr><td style='border: 1px solid #000; padding: 4px;'>VEJEZ</td><td style='border: 1px solid #000; padding: 4px;'>TAMIZAJE PARA CÁNCER DE COLON (SANGRE OCULTA EN MATERIA FECAL POR INMUNOQUÍMICA)</td><td style='border: 1px solid #000; padding: 4px; text-align: center;'>7</td></tr><tr><td style='border: 1px solid #000; padding: 4px;'>JUVENTUD</td><td style='border: 1px solid #000; padding: 4px;'>ATENCIÓN PRECONCEPCIONAL</td><td style='border: 1px solid #000; padding: 4px; text-align: center;'>26</td></tr><tr><td style='border: 1px solid #000; padding: 4px;'>VEJEZ</td><td style='border: 1px solid #000; padding: 4px;'>TAMIZAJE PARA CÁNCER DE MAMA (VALORACIÓN CLÍNICA DE LA MAMA)</td><td style='border: 1px solid #000; padding: 4px; text-align: center;'>26</td></tr><tr><td style='border: 1px solid #000; padding: 4px;'>PRIMERA INFANCIA</td><td style='border: 1px solid #000; padding: 4px;'>CONTROL POR MEDICINA GENERAL Y EDUCACIÓN</td><td style='border: 1px solid #000; padding: 4px; text-align: center;'>51</td></tr><tr><td style='border: 1px solid #000; padding: 4px;'>INFANCIA</td><td style='border: 1px solid #000; padding: 4px;'>CONTROL POR MEDICINA GENERAL Y EDUCACIÓN</td><td style='border: 1px solid #000; padding: 4px; text-align: center;'>35</td></tr><tr><td style='border: 1px solid #000; padding: 4px;'>ADOLESCENCIA</td><td style='border: 1px solid #000; padding: 4px;'>CONTROL POR MEDICINA GENERAL Y EDUCACIÓN</td><td style='border: 1px solid #000; padding: 4px; text-align: center;'>40</td></tr><tr><td style='border: 1px solid #000; padding: 4px;'>JUVENTUD</td><td style='border: 1px solid #000; padding: 4px;'>CONTROL POR MEDICINA GENERAL Y EDUCACIÓN</td><td style='border: 1px solid #000; padding: 4px; text-align: center;'>10</td></tr><tr><td style='border: 1px solid #000; padding: 4px;'>ADULTEZ</td><td style='border: 1px solid #000; padding: 4px;'>CONTROL POR MEDICINA GENERAL Y EDUCACIÓN</td><td style='border: 1px solid #000; padding: 4px; text-align: center;'>16</td></tr><tr><td style='border: 1px solid #000; padding: 4px;'>VEJEZ</td><td style='border: 1px solid #000; padding: 4px;'>CONTROL POR MEDICINA GENERAL Y EDUCACIÓN</td><td style='border: 1px solid #000; padding: 4px; text-align: center;'>40</td></tr></table>",
        "Participar en reuniones de seguimiento y evaluación de coordinación EBS.",
        "Cumplir las actividades asistenciales propias del ejercicio profesional como médico general.",
        "Acreditar afiliación y presentar pago de aportes a Seguridad Social Integral mensual.",
        "Remitir oportunamente informes, cronogramas, soportes físicos y magnéticos requeridos.",
        "Radicar la cuenta de cobro o factura con soportes exigidos.",
        "Cumplir obligaciones aplicables de la Resolución 518 de 2015.",
        "Entregar soportes físicos y digitalizados de registros de atención y firmas."
    ],
    "ENFERMERIA": [
        "Formular, implementar y realizar seguimiento al Plan Integral de Cuidado Primario (PICP) con énfasis materno-perinatal.",
        "Identificar y analizar los riesgos individuales, familiares y comunitarios.",
        "Brindar orientación e información clara sobre la oferta de servicios de salud.",
        "Promover la afiliación al Sistema General de Seguridad Social en Salud.",
        "Inducir a la demanda de servicios de salud y notificar eventos de interés en salud pública.",
        "Realizar canalización oportuna a los servicios de nivel primario y red de prestación.",
        "Hacer seguimiento al acceso efectivo y continuity de la atención.",
        "Promover espacios de concertación y mediación intercultural.",
        "Promover la articulación de los servicios de salud, sociales y ambientales.",
        "Socializar los resultados de la caracterización con las comunidades.",
        "Sistematizar, registrar y reportar la información en sistemas definidos por Minsalud.",
        "Identificar potencialidades y riesgos en entornos para priorizar intervenciones.",
        "Concertar y programar acciones sectoriales e intersectoriales para ejecutar el PICP.",
        "Programar y participar en trabajo colaborativo, capacitación y cuidado al cuidador.",
        "Implementar intervenciones del PICP que correspondan al perfil de enfermería.",
        "Gestionar la asistencia social requerida por personas y familias con necesidades.",
        "Activar los mecanismos de referencia y contrarreferencia.",
        "Identificar y gestionar barreras de acceso (geográficas, culturales, económicas).",
        "Diseñar y ejecutar estrategias de búsqueda activa y recuperación de inasistentes.",
        "Realizar registro oportuno y completo de las intervenciones de enfermería.",
        "Establecer estrategias de comunicación accesible e incluyente.",
        "Realizar seguimiento y ajustes periódicos al PICP.",
        "Revisar el avance de las acciones y metas del PICP y hacer ajustes.",
        "Identificar oportunidades de mejora continua en la implementación del PICP.",
        "Monitorear el cumplimiento de metas de cobertura poblacional.",
        "Programar y participar en reuniones de retroalimentación comunitaria.",
        "Aplicar guías de promoción, Resolución 3280, RIAS y guías de eventos de interés.",
        "Hacer uso adecuado de las TIC.",
        "Diligenciar los RIPS utilizando los códigos CIE-10.",
        "Diligenciar la historia clínica electrónica de manera clara, objetiva y completa.",
        "Diligenciar la historia clínica física cuando aplique.",
        "Hacer uso adecuado de equipos, medicamentos, dispositivos e insumos.",
        "Cumplir con la programación mensual informando ajustes.",
        "Cumplir con atenciones de familias en microterritorios asignados.",
        "Cumplir normas de bioseguridad y seguridad del paciente.",
        "Participar en las reuniones de seguimiento del EBS.",
        "Realizar registro y validación de valoraciones de enfermería respaldadas por educación.",
        "Contribuir al cumplimiento de metas del 100% de la población caracterizada.",
        "Realizar un total de seiscientas seis (606) atenciones individuales mensuales, en el marco de la Promoción y Mantenimiento de la Salud, de conformidad con la Resolución 3280 de 2018, los lineamientos técnicos vigentes del Ministerio de Salud y Protección Social y la planeación institucional de la Empresa Social del Estado NORTE 3 - E.S.E., distribuidas así:<br><br><table style='width:100%; border-collapse: collapse; font-size: 8px; margin-top: 5px;'><tr><th style='border: 1px solid #000; padding: 3px; background-color: #f2f2f2;'>GRUPO ETAREO</th><th style='border: 1px solid #000; padding: 3px; background-color: #f2f2f2;'>DESCRIPCIÓN DE LA ATENCIÓN</th><th style='border: 1px solid #000; padding: 3px; background-color: #f2f2f2;'>CLASIFICACIÓN</th><th style='border: 1px solid #000; padding: 3px; background-color: #f2f2f2; text-align: center;'>NO. ATENCIONES</th></tr><tr><td style='border: 1px solid #000; padding: 3px;'>ADOLESCENCIA</td><td style='border: 1px solid #000; padding: 3px;'>ATENCIÓN EN SALUD POR ENFERMERIA ASESORÍA EN ANTICONCEPCIÓN</td><td style='border: 1px solid #000; padding: 3px;'>ATENCION</td><td style='border: 1px solid #000; padding: 3px; text-align: center;'>10</td></tr><tr><td style='border: 1px solid #000; padding: 3px;'>ADOLESCENCIA</td><td style='border: 1px solid #000; padding: 3px;'>TAMIZAJE PARA ANEMIA - HEMOGLOBINA / HEMATOCRITO</td><td style='border: 1px solid #000; padding: 3px;'>TAMIZAJE</td><td style='border: 1px solid #000; padding: 3px; text-align: center;'>8</td></tr><tr><td style='border: 1px solid #000; padding: 3px;'>ADOLESCENCIA</td><td style='border: 1px solid #000; padding: 3px;'>PRUEBA DE EMBARAZO</td><td style='border: 1px solid #000; padding: 3px;'>LABORATORIO</td><td style='border: 1px solid #000; padding: 3px; text-align: center;'>5</td></tr><tr><td style='border: 1px solid #000; padding: 3px;'>ADOLESCENCIA</td><td style='border: 1px solid #000; padding: 3px;'>PRUEBA RÁPIDA PARA VIH (PRUEBA RÁPIDA PARA VIH (VIH 1 - VIH 2)</td><td style='border: 1px solid #000; padding: 3px;'>LABORATORIO</td><td style='border: 1px solid #000; padding: 3px; text-align: center;'>19</td></tr><tr><td style='border: 1px solid #000; padding: 3px;'>ADOLESCENCIA</td><td style='border: 1px solid #000; padding: 3px;'>PRUEBA TREPONÉMICA RÁPIDA PARA SÍFILIS</td><td style='border: 1px solid #000; padding: 3px;'>LABORATORIO</td><td style='border: 1px solid #000; padding: 3px; text-align: center;'>19</td></tr><tr><td style='border: 1px solid #000; padding: 3px;'>ADOLESCENCIA</td><td style='border: 1px solid #000; padding: 3px;'>ATENCION POR ENFERMERIA Y EDUCACION</td><td style='border: 1px solid #000; padding: 3px;'>ATENCION</td><td style='border: 1px solid #000; padding: 3px; text-align: center;'>15</td></tr><tr><td style='border: 1px solid #000; padding: 3px;'>ADULTEZ</td><td style='border: 1px solid #000; padding: 3px;'>ATENCIÓN EN SALUD POR ENFERMERIA ASESORÍA EN ANTICONCEPCIÓN</td><td style='border: 1px solid #000; padding: 3px;'>ATENCION</td><td style='border: 1px solid #000; padding: 3px; text-align: center;'>19</td></tr><tr><td style='border: 1px solid #000; padding: 3px;'>ADULTEZ</td><td style='border: 1px solid #000; padding: 3px;'>PRUEBA DE EMBARAZO</td><td style='border: 1px solid #000; padding: 3px;'>LABORATORIO</td><td style='border: 1px solid #000; padding: 3px; text-align: center;'>6</td></tr><tr><td style='border: 1px solid #000; padding: 3px;'>ADULTEZ</td><td style='border: 1px solid #000; padding: 3px;'>PRUEBA RÁPIDA PARA VIH (PRUEBA RÁPIDA PARA VIH (VIH 1 - VIH 2)</td><td style='border: 1px solid #000; padding: 3px;'>LABORATORIO</td><td style='border: 1px solid #000; padding: 3px; text-align: center;'>12</td></tr><tr><td style='border: 1px solid #000; padding: 3px;'>ADULTEZ</td><td style='border: 1px solid #000; padding: 3px;'>PRUEBA TREPONÉMICA RÁPIDA PARA SÍFILIS</td><td style='border: 1px solid #000; padding: 3px;'>LABORATORIO</td><td style='border: 1px solid #000; padding: 3px; text-align: center;'>15</td></tr><tr><td style='border: 1px solid #000; padding: 3px;'>ADULTEZ</td><td style='border: 1px solid #000; padding: 3px;'>COLESTEROL DE ALTA DENSIDAD HDL</td><td style='border: 1px solid #000; padding: 3px;'>LABORATORIO</td><td style='border: 1px solid #000; padding: 3px; text-align: center;'>13</td></tr><tr><td style='border: 1px solid #000; padding: 3px;'>ADULTEZ</td><td style='border: 1px solid #000; padding: 3px;'>COLESTEROL DE BAJA DENSIDAD LDL</td><td style='border: 1px solid #000; padding: 3px;'>LABORATORIO</td><td style='border: 1px solid #000; padding: 3px; text-align: center;'>13</td></tr><tr><td style='border: 1px solid #000; padding: 3px;'>ADULTEZ</td><td style='border: 1px solid #000; padding: 3px;'>COLESTEROL TOTAL</td><td style='border: 1px solid #000; padding: 3px;'>LABORATORIO</td><td style='border: 1px solid #000; padding: 3px; text-align: center;'>13</td></tr><tr><td style='border: 1px solid #000; padding: 3px;'>ADULTEZ</td><td style='border: 1px solid #000; padding: 3px;'>CREATININA EN SUERO U OTROS FLUIDOS</td><td style='border: 1px solid #000; padding: 3px;'>LABORATORIO</td><td style='border: 1px solid #000; padding: 3px; text-align: center;'>13</td></tr><tr><td style='border: 1px solid #000; padding: 3px;'>ADULTEZ</td><td style='border: 1px solid #000; padding: 3px;'>GLUCOSA EN SUERO LCR U OTRO FLUIDO DIFERENTE A ORINA</td><td style='border: 1px solid #000; padding: 3px;'>LABORATORIO</td><td style='border: 1px solid #000; padding: 3px; text-align: center;'>13</td></tr><tr><td style='border: 1px solid #000; padding: 3px;'>ADULTEZ</td><td style='border: 1px solid #000; padding: 3px;'>PRUEBA RÁPIDA PARA HEPATITIS B</td><td style='border: 1px solid #000; padding: 3px;'>LABORATORIO</td><td style='border: 1px solid #000; padding: 3px; text-align: center;'>12</td></tr><tr><td style='border: 1px solid #000; padding: 3px;'>ADULTEZ</td><td style='border: 1px solid #000; padding: 3px;'>PRUEBA RÁPIDA PARA HEPATITIS C</td><td style='border: 1px solid #000; padding: 3px;'>LABORATORIO</td><td style='border: 1px solid #000; padding: 3px; text-align: center;'>6</td></tr><tr><td style='border: 1px solid #000; padding: 3px;'>ADULTEZ</td><td style='border: 1px solid #000; padding: 3px;'>TAMIZAJE DE CÁNCER DE CUELLO UTERINO (TOMA DE MUESTRA CITOLOGIA VAGINAL)</td><td style='border: 1px solid #000; padding: 3px;'>TAMIZAJE</td><td style='border: 1px solid #000; padding: 3px; text-align: center;'>12</td></tr><tr><td style='border: 1px solid #000; padding: 3px;'>ADULTEZ</td><td style='border: 1px solid #000; padding: 3px;'>TRIGLICERIDOS</td><td style='border: 1px solid #000; padding: 3px;'>LABORATORIO</td><td style='border: 1px solid #000; padding: 3px; text-align: center;'>13</td></tr><tr><td style='border: 1px solid #000; padding: 3px;'>ADULTEZ</td><td style='border: 1px solid #000; padding: 3px;'>UROANÁLISIS</td><td style='border: 1px solid #000; padding: 3px;'>LABORATORIO</td><td style='border: 1px solid #000; padding: 3px; text-align: center;'>13</td></tr><tr><td style='border: 1px solid #000; padding: 3px;'>ADULTEZ</td><td style='border: 1px solid #000; padding: 3px;'>TAMIZAJE DE CÁNCER DE CUELLO UTERINO (ADN VPH)</td><td style='border: 1px solid #000; padding: 3px;'>TAMIZAJE</td><td style='border: 1px solid #000; padding: 3px; text-align: center;'>8</td></tr><tr><td style='border: 1px solid #000; padding: 3px;'>ADULTEZ</td><td style='border: 1px solid #000; padding: 3px;'>TAMIZAJE DE CANCER DE CUELLO UTERINO (ESTUDIO DE COLORACION BASICA EN CITOLOGIA VAGINAL)</td><td style='border: 1px solid #000; padding: 3px;'>TAMIZAJE</td><td style='border: 1px solid #000; padding: 3px; text-align: center;'>12</td></tr><tr><td style='border: 1px solid #000; padding: 3px;'>INFANCIA</td><td style='border: 1px solid #000; padding: 3px;'>TAMIZAJE PARA ANEMIA - HEMOGLOBINA / HEMATOCRITO</td><td style='border: 1px solid #000; padding: 3px;'>TAMIZAJE</td><td style='border: 1px solid #000; padding: 3px; text-align: center;'>5</td></tr><tr><td style='border: 1px solid #000; padding: 3px;'>INFANCIA</td><td style='border: 1px solid #000; padding: 3px;'>ATENCION POR ENFERMERIA Y EDUCACION</td><td style='border: 1px solid #000; padding: 3px;'>ATENCION</td><td style='border: 1px solid #000; padding: 3px; text-align: center;'>13</td></tr><tr><td style='border: 1px solid #000; padding: 3px;'>JUVENTUD</td><td style='border: 1px solid #000; padding: 3px;'>ATENCIÓN EN SALUD POR ENFERMERIA ASESORÍA EN ANTICONCEPCIÓN</td><td style='border: 1px solid #000; padding: 3px;'>ATENCION</td><td style='border: 1px solid #000; padding: 3px; text-align: center;'>8</td></tr><tr><td style='border: 1px solid #000; padding: 3px;'>JUVENTUD</td><td style='border: 1px solid #000; padding: 3px;'>PRUEBA DE EMBARAZO</td><td style='border: 1px solid #000; padding: 3px;'>LABORATORIO</td><td style='border: 1px solid #000; padding: 3px; text-align: center;'>5</td></tr><tr><td style='border: 1px solid #000; padding: 3px;'>JUVENTUD</td><td style='border: 1px solid #000; padding: 3px;'>PRUEBA RÁPIDA PARA VIH (PRUEBA RÁPIDA PARA VIH (VIH 1 - VIH 2)</td><td style='border: 1px solid #000; padding: 3px;'>LABORATORIO</td><td style='border: 1px solid #000; padding: 3px; text-align: center;'>37</td></tr><tr><td style='border: 1px solid #000; padding: 3px;'>JUVENTUD</td><td style='border: 1px solid #000; padding: 3px;'>PRUEBA TREPONÉMICA RÁPIDA PARA SÍFILIS</td><td style='border: 1px solid #000; padding: 3px;'>LABORATORIO</td><td style='border: 1px solid #000; padding: 3px; text-align: center;'>37</td></tr><tr><td style='border: 1px solid #000; padding: 3px;'>JUVENTUD</td><td style='border: 1px solid #000; padding: 3px;'>COLESTEROL DE ALTA DENSIDAD HDL</td><td style='border: 1px solid #000; padding: 3px;'>LABORATORIO</td><td style='border: 1px solid #000; padding: 3px; text-align: center;'>6</td></tr><tr><td style='border: 1px solid #000; padding: 3px;'>JUVENTUD</td><td style='border: 1px solid #000; padding: 3px;'>COLESTEROL DE BAJA DENSIDAD LDL</td><td style='border: 1px solid #000; padding: 3px;'>LABORATORIO</td><td style='border: 1px solid #000; padding: 3px; text-align: center;'>6</td></tr><tr><td style='border: 1px solid #000; padding: 3px;'>JUVENTUD</td><td style='border: 1px solid #000; padding: 3px;'>COLESTEROL TOTAL</td><td style='border: 1px solid #000; padding: 3px;'>LABORATORIO</td><td style='border: 1px solid #000; padding: 3px; text-align: center;'>6</td></tr><tr><td style='border: 1px solid #000; padding: 3px;'>JUVENTUD</td><td style='border: 1px solid #000; padding: 3px;'>CREATININA EN SUERO U OTROS FLUIDOS</td><td style='border: 1px solid #000; padding: 3px;'>LABORATORIO</td><td style='border: 1px solid #000; padding: 3px; text-align: center;'>6</td></tr><tr><td style='border: 1px solid #000; padding: 3px;'>JUVENTUD</td><td style='border: 1px solid #000; padding: 3px;'>GLUCOSA EN SUERO LCR U OTRO FLUIDO DIFERENTE A ORINA</td><td style='border: 1px solid #000; padding: 3px;'>LABORATORIO</td><td style='border: 1px solid #000; padding: 3px; text-align: center;'>6</td></tr><tr><td style='border: 1px solid #000; padding: 3px;'>JUVENTUD</td><td style='border: 1px solid #000; padding: 3px;'>PRUEBA RÁPIDA PARA HEPATITIS B</td><td style='border: 1px solid #000; padding: 3px;'>LABORATORIO</td><td style='border: 1px solid #000; padding: 3px; text-align: center;'>37</td></tr><tr><td style='border: 1px solid #000; padding: 3px;'>JUVENTUD</td><td style='border: 1px solid #000; padding: 3px;'>PRUEBA RÁPIDA PARA HEPATITIS C</td><td style='border: 1px solid #000; padding: 3px;'>LABORATORIO</td><td style='border: 1px solid #000; padding: 3px; text-align: center;'>5</td></tr><tr><td style='border: 1px solid #000; padding: 3px;'>JUVENTUD</td><td style='border: 1px solid #000; padding: 3px;'>TAMIZAJE DE CANCER DE CUELLO UTERINO (TOMA DE MUESTRA CITOLOGIA VAGINAL)</td><td style='border: 1px solid #000; padding: 3px;'>TAMIZAJE</td><td style='border: 1px solid #000; padding: 3px; text-align: center;'>8</td></tr><tr><td style='border: 1px solid #000; padding: 3px;'>JUVENTUD</td><td style='border: 1px solid #000; padding: 3px;'>TRIGLICERIDOS</td><td style='border: 1px solid #000; padding: 3px;'>LABORATORIO</td><td style='border: 1px solid #000; padding: 3px; text-align: center;'>6</td></tr><tr><td style='border: 1px solid #000; padding: 3px;'>JUVENTUD</td><td style='border: 1px solid #000; padding: 3px;'>UROANÁLISIS</td><td style='border: 1px solid #000; padding: 3px;'>LABORATORIO</td><td style='border: 1px solid #000; padding: 3px; text-align: center;'>6</td></tr><tr><td style='border: 1px solid #000; padding: 3px;'>PRIMERA INFANCIA</td><td style='border: 1px solid #000; padding: 3px;'>TAMIZAJE PARA ANEMIA - HEMOGLOBINA / HEMATOCRITO</td><td style='border: 1px solid #000; padding: 3px;'>TAMIZAJE</td><td style='border: 1px solid #000; padding: 3px; text-align: center;'>5</td></tr><tr><td style='border: 1px solid #000; padding: 3px;'>PRIMERA INFANCIA</td><td style='border: 1px solid #000; padding: 3px;'>ATENCION POR ENFERMERIA Y EDUCACION</td><td style='border: 1px solid #000; padding: 3px;'>ATENCION</td><td style='border: 1px solid #000; padding: 3px; text-align: center;'>19</td></tr><tr><td style='border: 1px solid #000; padding: 3px;'>VEJEZ</td><td style='border: 1px solid #000; padding: 3px;'>ATENCIÓN EN SALUD POR ENFERMERIA ASESORÍA EN ANTICONCEPCIÓN</td><td style='border: 1px solid #000; padding: 3px;'>ATENCION</td><td style='border: 1px solid #000; padding: 3px; text-align: center;'>6</td></tr><tr><td style='border: 1px solid #000; padding: 3px;'>VEJEZ</td><td style='border: 1px solid #000; padding: 3px;'>PRUEBA RÁPIDA PARA VIH (PRUEBA RÁPIDA PARA VIH (VIH 1 - VIH 2)</td><td style='border: 1px solid #000; padding: 3px;'>LABORATORIO</td><td style='border: 1px solid #000; padding: 3px; text-align: center;'>13</td></tr><tr><td style='border: 1px solid #000; padding: 3px;'>VEJEZ</td><td style='border: 1px solid #000; padding: 3px;'>PRUEBA TREPONÉMICA RÁPIDA PARA SÍFILIS</td><td style='border: 1px solid #000; padding: 3px;'>LABORATORIO</td><td style='border: 1px solid #000; padding: 3px; text-align: center;'>13</td></tr><tr><td style='border: 1px solid #000; padding: 3px;'>VEJEZ</td><td style='border: 1px solid #000; padding: 3px;'>COLESTEROL DE ALTA DENSIDAD HDL</td><td style='border: 1px solid #000; padding: 3px;'>LABORATORIO</td><td style='border: 1px solid #000; padding: 3px; text-align: center;'>8</td></tr><tr><td style='border: 1px solid #000; padding: 3px;'>VEJEZ</td><td style='border: 1px solid #000; padding: 3px;'>COLESTEROL DE BAJA DENSIDAD LDL</td><td style='border: 1px solid #000; padding: 3px;'>LABORATORIO</td><td style='border: 1px solid #000; padding: 3px; text-align: center;'>8</td></tr><tr><td style='border: 1px solid #000; padding: 3px;'>VEJEZ</td><td style='border: 1px solid #000; padding: 3px;'>COLESTEROL TOTAL</td><td style='border: 1px solid #000; padding: 3px;'>LABORATORIO</td><td style='border: 1px solid #000; padding: 3px; text-align: center;'>8</td></tr><tr><td style='border: 1px solid #000; padding: 3px;'>VEJEZ</td><td style='border: 1px solid #000; padding: 3px;'>CREATININA EN SUERO U OTROS FLUIDOS</td><td style='border: 1px solid #000; padding: 3px;'>LABORATORIO</td><td style='border: 1px solid #000; padding: 3px; text-align: center;'>8</td></tr><tr><td style='border: 1px solid #000; padding: 3px;'>VEJEZ</td><td style='border: 1px solid #000; padding: 3px;'>GLUCOSA EN SUERO LCR U OTRO FLUIDO DIFERENTE A ORINA</td><td style='border: 1px solid #000; padding: 3px;'>LABORATORIO</td><td style='border: 1px solid #000; padding: 3px; text-align: center;'>8</td></tr><tr><td style='border: 1px solid #000; padding: 3px;'>VEJEZ</td><td style='border: 1px solid #000; padding: 3px;'>PRUEBA RÁPIDA PARA HEPATITIS B</td><td style='border: 1px solid #000; padding: 3px;'>LABORATORIO</td><td style='border: 1px solid #000; padding: 3px; text-align: center;'>13</td></tr><tr><td style='border: 1px solid #000; padding: 3px;'>VEJEZ</td><td style='border: 1px solid #000; padding: 3px;'>PRUEBA RÁPIDA PARA HEPATITIS C</td><td style='border: 1px solid #000; padding: 3px;'>LABORATORIO</td><td style='border: 1px solid #000; padding: 3px; text-align: center;'>5</td></tr><tr><td style='border: 1px solid #000; padding: 3px;'>VEJEZ</td><td style='border: 1px solid #000; padding: 3px;'>TAMIZAJE DE CÁNCER DE CUELLO UTERINO (TOMA DE MUESTRA CITOLOGIA VAGINAL)</td><td style='border: 1px solid #000; padding: 3px;'>TAMIZAJE</td><td style='border: 1px solid #000; padding: 3px; text-align: center;'>5</td></tr><tr><td style='border: 1px solid #000; padding: 3px;'>VEJEZ</td><td style='border: 1px solid #000; padding: 3px;'>TRIGLICERIDOS</td><td style='border: 1px solid #000; padding: 3px;'>LABORATORIO</td><td style='border: 1px solid #000; padding: 3px; text-align: center;'>8</td></tr><tr><td style='border: 1px solid #000; padding: 3px;'>VEJEZ</td><td style='border: 1px solid #000; padding: 3px;'>UROANÁLISIS</td><td style='border: 1px solid #000; padding: 3px;'>LABORATORIO</td><td style='border: 1px solid #000; padding: 3px; text-align: center;'>8</td></tr><tr><td style='border: 1px solid #000; padding: 3px;'>VEJEZ</td><td style='border: 1px solid #000; padding: 3px;'>TAMIZAJE DE CÁNCER DE CUELLO UTERINO (ADN VPH)</td><td style='border: 1px solid #000; padding: 3px;'>TAMIZAJE</td><td style='border: 1px solid #000; padding: 3px; text-align: center;'>5</td></tr></table>",
        "Contribuir a la operatividad y articulación del EBS.",
        "Cumplir con los lineamientos de capacitación definidos.",
        "Acreditar Seguridad Social, presentar informes de ejecución, atender requerimientos del supervisor, custodiar equipos, abstenerse de usar recursos institucionales a otros fines y garantizar confidencialidad de la historia clínica."
    ],
    "PSICOLOGIA": [
        "Ejecutar intervenciones colectivas en salud mental y psicosocial (redes comunitarias, centros de escucha).",
        "Participar en la formulación, implementación y seguimiento del PICP con intervenciones en salud mental.",
        "Identificar y analizar los riesgos psicosociales individuales, familiares y comunitarios.",
        "Brindar orientación psicosocial e información clara sobre oferta de servicios en salud mental.",
        "Inducir a la demanda de servicios de salud mental priorizando eventos de salud pública.",
        "Realizar canalización oportuna a los servicios de salud primaria en salud mental.",
        "Hacer seguimiento al acceso efectivo y continuidad de la atención psicosocial.",
        "Promover espacios de conciliación, mediación y abordaje intercultural.",
        "Promover y gestionar la articulación intersectorial con servicios sociales y educativos.",
        "Socializar con las comunidades los resultados de la caracterización psicosocial.",
        "Sistematizar, registrar y reportar la información en los registros definidos.",
        "Identificar potencialidades, factores protectores y riesgos psicosociales del entorno.",
        "Concertar y programar acciones sectoriales enfocadas en intervenciones psicosociales.",
        "Programar y participar en acciones de trabajo colaborativo y cuidado al cuidador.",
        "Implementar intervenciones colectivas psicosociales y gestionar atenciones individuales.",
        "Gestionar la asistencia psicosocial requerida en articulación con el territorio.",
        "Activar mecanismos de referencia y contrarreferencia en salud mental.",
        "Identificar y gestionar barreras de acceso a la atención psicosocial.",
        "Diseñar estrategias de búsqueda activa y recuperación de personas en salud mental.",
        "Participar en reuniones de análisis de casos y cuidado al cuidador del equipo.",
        "Registrar oportuna y completamente la información de intervenciones psicosociales.",
        "Establecer mecanismos de comunicación accesible e incluyente.",
        "Utilizar adecuadamente las TIC.",
        "Diligenciar los RIPS utilizando códigos CIE-10.",
        "Diligenciar de manera clara y pertinente la historia clínica electrónica.",
        "Diligenciar la historia clínica física cuando aplique.",
        "Hacer uso adecuado de equipos, herramientas e insumos.",
        "Cumplir con la programación informando ajustes.",
        "Cumplir con atenciones de familias en microterritorios.",
        "Cumplir con normas de bioseguridad.",
        "Participar en reuniones de seguimiento de coordinación EBS.",
        "Acatar lineamientos técnicos y operativos del Coordinador EBS.",
        "Realizar registro de valoraciones psicosociales respaldadas por educación en salud mental (Res 3280).",
        "Contribuir al cumplimiento de metas 100%: Consulta psicología, aplicación tamizajes SPA, escala sobrecarga cuidador, atención a víctimas conflicto.",
        "Realizar un total de 500 atenciones individuales mensuales en el marco de Promoción y Mantenimiento.",
        "Diligenciar tamizajes en software institucional y plantilla de Minsalud.",
        "Cumplir con el plan de capacitaciones de Minsalud y E.S.E. NORTE 3."
    ],
    "SALUD ORAL": [
        "Ejecutar actividades de higiene oral y promoción de salud bucal (Resolución 3280).",
        "Diligenciar de manera oportuna los RIPS con códigos CIE-10.",
        "Registrar de forma clara la información en la historia clínica electrónica.",
        "Diligenciar la historia clínica física cuando aplique.",
        "Brindar orientación sobre oferta de servicios de salud oral.",
        "Apoyar promoción de afiliación a Seguridad Social.",
        "Canalizar a las personas hacia servicios de salud oral bajo orientación del odontólogo.",
        "Desarrollar actividades de demanda inducida comunitaria en salud oral.",
        "Ejecutar acciones de búsqueda activa y seguimiento de salud bucal.",
        "Apoyar la implementación de intervenciones colectivas del PICP en salud oral.",
        "Articular con servicios sociales acciones de apoyo para usuarios.",
        "Identificar riesgos en entornos para priorización de intervenciones orales.",
        "Apoyar la logística de las actividades del EBS.",
        "Apoyar seguimiento y ajuste de los PICP desde componente bucal.",
        "Contribuir al cumplimiento de metas de cobertura.",
        "Utilizar de manera adecuada las TIC.",
        "Cumplir normas de bioseguridad en salud oral.",
        "Participar en las reuniones de seguimiento y evaluación del EBS.",
        "Aplicar lineamientos técnicos del odontólogo y Coordinador EBS.",
        "Acreditar pago a Seguridad Social Integral.",
        "Presentar oportunamente documentación para seguimiento contractual.",
        "Radicar cuenta de cobro o factura en plazos establecidos.",
        "Asistir a jornadas de capacitación de la E.S.E. o Minsalud.",
        "Realizar un total de quinientas cincuenta y cuatro (554) atenciones individuales mensuales, en el marco de la Promoción y Mantenimiento de la Salud, de conformidad con la Resolución 3280 de 2018, los lineamientos técnicos vigentes del Ministerio de Salud y Protección Social y la planeación institucional de la Empresa Social del Estado NORTE 3 - E.S.E., distribuidas así:<br><br><table style='width:100%; border-collapse: collapse; font-size: 9px; margin-top: 5px;'><tr><th style='border: 1px solid #000; padding: 4px; background-color: #f2f2f2;'>GRUPO ETAREO</th><th style='border: 1px solid #000; padding: 4px; background-color: #f2f2f2;'>DESCRIPCIÓN DE LA ATENCIÓN</th><th style='border: 1px solid #000; padding: 4px; background-color: #f2f2f2; text-align: center;'>NO. ATENCIONES</th></tr><tr><td style='border: 1px solid #000; padding: 4px;'>PRIMERA INFANCIA</td><td style='border: 1px solid #000; padding: 4px;'>APLICACIÓN DE BARNIZ DE FLÚOR</td><td style='border: 1px solid #000; padding: 4px; text-align: center;'>46</td></tr><tr><td style='border: 1px solid #000; padding: 4px;'>PRIMERA INFANCIA</td><td style='border: 1px solid #000; padding: 4px;'>PROFILAXIS Y REMOCIÓN DE PLACA BACTERIANA</td><td style='border: 1px solid #000; padding: 4px; text-align: center;'>46</td></tr><tr><td style='border: 1px solid #000; padding: 4px;'>INFANCIA</td><td style='border: 1px solid #000; padding: 4px;'>APLICACIÓN DE BARNIZ DE FLÚOR</td><td style='border: 1px solid #000; padding: 4px; text-align: center;'>68</td></tr><tr><td style='border: 1px solid #000; padding: 4px;'>INFANCIA</td><td style='border: 1px solid #000; padding: 4px;'>PROFILAXIS Y REMOCIÓN DE PLACA BACTERIANA</td><td style='border: 1px solid #000; padding: 4px; text-align: center;'>68</td></tr><tr><td style='border: 1px solid #000; padding: 4px;'>ADOLESCENCIA</td><td style='border: 1px solid #000; padding: 4px;'>APLICACIÓN DE BARNIZ DE FLÚOR</td><td style='border: 1px solid #000; padding: 4px; text-align: center;'>78</td></tr><tr><td style='border: 1px solid #000; padding: 4px;'>ADOLESCENCIA</td><td style='border: 1px solid #000; padding: 4px;'>PROFILAXIS Y REMOCIÓN DE PLACA BACTERIANA</td><td style='border: 1px solid #000; padding: 4px; text-align: center;'>78</td></tr><tr><td style='border: 1px solid #000; padding: 4px;'>JUVENTUD</td><td style='border: 1px solid #000; padding: 4px;'>PROFILAXIS Y REMOCIÓN DE PLACA BACTERIANA</td><td style='border: 1px solid #000; padding: 4px; text-align: center;'>63</td></tr><tr><td style='border: 1px solid #000; padding: 4px;'>ADULTEZ</td><td style='border: 1px solid #000; padding: 4px;'>PROFILAXIS Y REMOCIÓN DE PLACA BACTERIANA</td><td style='border: 1px solid #000; padding: 4px; text-align: center;'>73</td></tr><tr><td style='border: 1px solid #000; padding: 4px;'>VEJEZ</td><td style='border: 1px solid #000; padding: 4px;'>PROFILAXIS Y REMOCIÓN DE PLACA BACTERIANA</td><td style='border: 1px solid #000; padding: 4px; text-align: center;'>34</td></tr></table>",
        "Desarrollar actividades educativas comunitarias (charlas, talleres).",
        "Brindar apoyo en atención inicial de urgencia odontológica y canalizar."
    ],
    "GESTOR COMUNITARIO": [
        "Participar en la priorización de los microterritorios del municipio asignado.",
        "Apoyar la elaboración de cartografía social de los microterritorios priorizados.",
        "Actuar como enlace comunitario entre el Equipo de Salud Territorial (EST) y las comunidades.",
        "Apoyar el relacionamiento inicial entre el EST y la comunidad, promoviendo confianza.",
        "Contribuir al análisis de los determinantes sociales aportando información del contexto.",
        "Identificar tempranamente situaciones de riesgo a nivel individual y canalizar al equipo.",
        "Fortalecer actividades de información y educación de la población hacia servicios de salud.",
        "Apoyar el seguimiento familiar a las acciones definidas en el PICP.",
        "Contribuir al diseño de estrategias de comunicación accesible e incluyente.",
        "Apoyar el seguimiento y ajuste de los PICP de acuerdo con resultados comunitarios.",
        "Apoyar la revisión del avance de metas establecidas en los PICP.",
        "Contribuir al seguimiento de metas de cobertura en la población asignada.",
        "Participar en las reuniones de retroalimentación comunitaria.",
        "Gestionar asistencia social requerida por personas con necesidades, articulando con el territorio.",
        "Identificar potencialidades y riesgos en los entornos comunitarios.",
        "Apoyar la programación, planeación y logística de actividades del componente comunitario.",
        "Participar en reuniones de seguimiento y evaluación de coordinación EBS.",
        "Ejecutar actividades propias del rol relacionadas con Atención Primaria en Salud.",
        "Acreditar afiliación y pago de Seguridad Social Integral.",
        "Remitir informes, cronogramas y documentos requeridos por la supervisión.",
        "Radicar cuenta de cobro al finalizar la ejecución.",
        "Cumplir con disposiciones de la Resolución 518 de 2015 en salud pública.",
        "Entregar soportes físicos y digitales de registros de firmas y acciones.",
        "Actuar conforme a lineamientos técnicos y operativos del programa EBS."
    ],
    "AUXILIAR VACUNACION": [
        "Ejecutar actividades como Auxiliar de Enfermería según lineamientos del MIAS y APS.",
        "Realizar la identificación de riesgos y necesidades de la población asignada (Res 3280).",
        "Registrar la información de identificación de riesgos en instrumentos de la E.S.E.",
        "Promover la afiliación de la población a Seguridad Social en Salud.",
        "Apoyar la canalización de usuarios hacia la red de prestación primaria.",
        "Ejecutar acciones de demanda inducida comunitaria y búsqueda activa.",
        "Apoyar la implementación de intervenciones del PICP a cargo del Equipo de Salud.",
        "Articular con servicios sociales acciones de asistencia para personas con necesidades.",
        "Identificar riesgos en entornos para priorizar intervenciones.",
        "Apoyar la logística de las salidas extramurales a los microterritorios.",
        "Apoyar la planeación y desarrollo de actividades logísticas del EBS.",
        "Apoyar el registro de intervenciones en los RIPS con códigos CIE-10.",
        "Apoyar el seguimiento al diligenciamiento de historias clínicas y formatos.",
        "Desarrollar actividades de educación para la salud dirigidas a la población.",
        "Utilizar adecuadamente las TIC en actividades asistenciales y registro.",
        "Custodiar, conservar y hacer uso adecuado de equipos e insumos.",
        "Hacer uso responsable de medicamentos conforme a protocolos.",
        "Cumplir con normas de bioseguridad del Manual de la E.S.E.",
        "Participar en las jornadas de capacitación y actualización de Minsalud/E.S.E.",
        "Presentar informes periódicos de actividades objetivas y verificables.",
        "Acreditar pago de Seguridad Social Integral y presentar soportes.",
        "Radicar cuenta de cobro de manera mensual con soportes requeridos.",
        "Apoyar la identificación de riesgos aplicando instrumentos definidos por la E.S.E.",
        "Realizar un total de quinientas ochenta y siete (587) atenciones individuales mensuales, en el marco del Programa Ampliado de Inmunizaciones (PAI) y de las acciones de Promoción y Mantenimiento de la Salud, de conformidad con la Resolución 3280 de 2018, los lineamientos técnicos vigentes del Ministerio de Salud y Protección Social, las normas del PAI y la planeación institucional de la Empresa Social del Estado NORTE 3 - E.S.E., las cuales se ejecutarán mediante actividades de identificación de población objeto del PAI, aplicación de biológicos conforme al esquema nacional de vacunación, seguimiento a esquemas incompletos y registro oportuno y completo de la información en el aplicativo PAIWEB, distribuidas así:<br><br><table style='width:100%; border-collapse: collapse; font-size: 9px; margin-top: 5px;'><tr><th style='border: 1px solid #000; padding: 4px; background-color: #f2f2f2;'>GRUPO ETAREO</th><th style='border: 1px solid #000; padding: 4px; background-color: #f2f2f2;'>DESCRIPCIÓN DE LA ATENCIÓN</th><th style='border: 1px solid #000; padding: 4px; background-color: #f2f2f2; text-align: center;'>META</th></tr><tr><td style='border: 1px solid #000; padding: 4px;'>PRIMERA INFANCIA</td><td style='border: 1px solid #000; padding: 4px;'>ADMINISTRACIÓN VACUNA SARS COV 2 [COVID-19]</td><td style='border: 1px solid #000; padding: 4px; text-align: center;'>11</td></tr><tr><td style='border: 1px solid #000; padding: 4px;'>PRIMERA INFANCIA</td><td style='border: 1px solid #000; padding: 4px;'>VACUNACION COMBINADA CONTRA DIFTERIATETANOS Y TOS FERINA (DPT)</td><td style='border: 1px solid #000; padding: 4px; text-align: center;'>6</td></tr><tr><td style='border: 1px solid #000; padding: 4px;'>PRIMERA INFANCIA</td><td style='border: 1px solid #000; padding: 4px;'>VACUNACION CONTRA FIEBRE AMARILLA</td><td style='border: 1px solid #000; padding: 4px; text-align: center;'>11</td></tr><tr><td style='border: 1px solid #000; padding: 4px;'>PRIMERA INFANCIA</td><td style='border: 1px solid #000; padding: 4px;'>VACUNACION CONTRA HEPATITIS A</td><td style='border: 1px solid #000; padding: 4px; text-align: center;'>11</td></tr><tr><td style='border: 1px solid #000; padding: 4px;'>PRIMERA INFANCIA</td><td style='border: 1px solid #000; padding: 4px;'>VACUNACION CONTRA HEPATITIS B</td><td style='border: 1px solid #000; padding: 4px; text-align: center;'>6</td></tr><tr><td style='border: 1px solid #000; padding: 4px;'>PRIMERA INFANCIA</td><td style='border: 1px solid #000; padding: 4px;'>VACUNACION CONTRA INFLUENZA</td><td style='border: 1px solid #000; padding: 4px; text-align: center;'>18</td></tr><tr><td style='border: 1px solid #000; padding: 4px;'>PRIMERA INFANCIA</td><td style='border: 1px solid #000; padding: 4px;'>VACUNACION CONTRA NEUMOCOCO</td><td style='border: 1px solid #000; padding: 4px; text-align: center;'>13</td></tr><tr><td style='border: 1px solid #000; padding: 4px;'>PRIMERA INFANCIA</td><td style='border: 1px solid #000; padding: 4px;'>VACUNACION CONTRA POLIOMILITIS (VOP O IVP)</td><td style='border: 1px solid #000; padding: 4px; text-align: center;'>29</td></tr><tr><td style='border: 1px solid #000; padding: 4px;'>PRIMERA INFANCIA</td><td style='border: 1px solid #000; padding: 4px;'>VACUNACION CONTRA ROTAVIRUS</td><td style='border: 1px solid #000; padding: 4px; text-align: center;'>13</td></tr><tr><td style='border: 1px solid #000; padding: 4px;'>PRIMERA INFANCIA</td><td style='border: 1px solid #000; padding: 4px;'>VACUNACION CONTRA TUBERCULOSIS (BCG)</td><td style='border: 1px solid #000; padding: 4px; text-align: center;'>6</td></tr><tr><td style='border: 1px solid #000; padding: 4px;'>PRIMERA INFANCIA</td><td style='border: 1px solid #000; padding: 4px;'>VACUNACION CONTRA VARICELA</td><td style='border: 1px solid #000; padding: 4px; text-align: center;'>13</td></tr><tr><td style='border: 1px solid #000; padding: 4px;'>PRIMERA INFANCIA</td><td style='border: 1px solid #000; padding: 4px;'>VACUNACION PENTAVALENTE</td><td style='border: 1px solid #000; padding: 4px; text-align: center;'>18</td></tr><tr><td style='border: 1px solid #000; padding: 4px;'>PRIMERA INFANCIA</td><td style='border: 1px solid #000; padding: 4px;'>VACUNACIÓN TRIPLE VIRAL</td><td style='border: 1px solid #000; padding: 4px; text-align: center;'>18</td></tr><tr><td style='border: 1px solid #000; padding: 4px;'>INFANCIA</td><td style='border: 1px solid #000; padding: 4px;'>ADMINISTRACIÓN VACUNA SARS COV 2 [COVID-19]</td><td style='border: 1px solid #000; padding: 4px; text-align: center;'>16</td></tr><tr><td style='border: 1px solid #000; padding: 4px;'>INFANCIA</td><td style='border: 1px solid #000; padding: 4px;'>ADMINISTRACION DE TOXOIDE DE TETANOS (TD)</td><td style='border: 1px solid #000; padding: 4px; text-align: center;'>24</td></tr><tr><td style='border: 1px solid #000; padding: 4px;'>INFANCIA</td><td style='border: 1px solid #000; padding: 4px;'>APLICACIÓN DE VPH</td><td style='border: 1px solid #000; padding: 4px; text-align: center;'>29</td></tr><tr><td style='border: 1px solid #000; padding: 4px;'>ADOLESCENCIA</td><td style='border: 1px solid #000; padding: 4px;'>ADMINISTRACIÓN VACUNA SARS COV 2 [COVID-19]</td><td style='border: 1px solid #000; padding: 4px; text-align: center;'>16</td></tr><tr><td style='border: 1px solid #000; padding: 4px;'>ADOLESCENCIA</td><td style='border: 1px solid #000; padding: 4px;'>ADMINISTRACION DE TOXOIDE DE TETANOS (TD)</td><td style='border: 1px solid #000; padding: 4px; text-align: center;'>18</td></tr><tr><td style='border: 1px solid #000; padding: 4px;'>ADOLESCENCIA</td><td style='border: 1px solid #000; padding: 4px;'>APLICACIÓN DE VPH</td><td style='border: 1px solid #000; padding: 4px; text-align: center;'>55</td></tr><tr><td style='border: 1px solid #000; padding: 4px;'>JUVENTUD</td><td style='border: 1px solid #000; padding: 4px;'>ADMINISTRACIÓN VACUNA SARS COV 2 [COVID-19]</td><td style='border: 1px solid #000; padding: 4px; text-align: center;'>24</td></tr><tr><td style='border: 1px solid #000; padding: 4px;'>JUVENTUD</td><td style='border: 1px solid #000; padding: 4px;'>ADMINISTRACION DE TOXOIDE DE TETANOS (TD)</td><td style='border: 1px solid #000; padding: 4px; text-align: center;'>13</td></tr><tr><td style='border: 1px solid #000; padding: 4px;'>ADULTEZ</td><td style='border: 1px solid #000; padding: 4px;'>ADMINISTRACIÓN VACUNA SARS COV 2 [COVID-19]</td><td style='border: 1px solid #000; padding: 4px; text-align: center;'>50</td></tr><tr><td style='border: 1px solid #000; padding: 4px;'>ADULTEZ</td><td style='border: 1px solid #000; padding: 4px;'>ADMINISTRACION DE TOXOIDE DE TETANOS (TD)</td><td style='border: 1px solid #000; padding: 4px; text-align: center;'>18</td></tr><tr><td style='border: 1px solid #000; padding: 4px;'>VEJEZ</td><td style='border: 1px solid #000; padding: 4px;'>ADMINISTRACIÓN VACUNA SARS COV 2 [COVID-19]</td><td style='border: 1px solid #000; padding: 4px; text-align: center;'>27</td></tr><tr><td style='border: 1px solid #000; padding: 4px;'>VEJEZ</td><td style='border: 1px solid #000; padding: 4px;'>VACUNACION CONTRA INFLUENZA</td><td style='border: 1px solid #000; padding: 4px; text-align: center;'>124</td></tr></table>"
    ],
    "AUXILIAR ENFERMERIA": [
        "Ejecutar actividades propias de Auxiliar de Enfermería según lineamientos MIAS y APS.",
        "Realizar la identificación de riesgos y necesidades de la población (Res 3280).",
        "Registrar información derivada de la identificación de riesgos en instrumentos.",
        "Promover la afiliación de la población a Seguridad Social en Salud.",
        "Apoyar la canalización de usuarios hacia la red de nivel primario.",
        "Ejecutar acciones de demanda inducida comunitaria, búsqueda activa y control.",
        "Apoyar la implementación de intervenciones del PICP a cargo del EBS.",
        "Articular con servicios sociales acciones dirigidas a personas con necesidades.",
        "Identificar riesgos y potencialidades en los entornos sociosanitarios.",
        "Apoyar logística de salidas extramurales a territorios y microterritorios.",
        "Apoyar la planeación y desarrollo logístico de actividades del EBS.",
        "Apoyar el registro de intervenciones en registros administrativos (RIPS).",
        "Apoyar seguimiento al diligenciamiento de historias clínicas y formatos.",
        "Desarrollar actividades de educación para la salud según contexto sociocultural.",
        "Utilizar adecuadamente las TIC.",
        "Custodiar equipos, herramientas, insumos y bienes entregados para ejecución.",
        "Hacer uso responsable de medicamentos, dispositivos médicos e insumos.",
        "Cumplir normas de bioseguridad según manual adoptado por E.S.E.",
        "Participar en jornadas de capacitación de la E.S.E. o Ministerio de Salud.",
        "Presentar informes periódicos de actividades objetivas y verificables.",
        "Acreditar pago a Seguridad Social Integral.",
        "Radicar cuenta de cobro mensual con soportes correspondientes.",
        "Apoyar identificación de riesgos y necesidades mediante aplicación de instrumentos.",
        "Cumplir como mínimo con metas de identificación mensual: 210 formularios de familias o 483 personas caracterizadas."
    ]
}

HONORARIOS_POR_PERFIL = {
    "MEDICINA": 8000000,
    "ENFERMERIA": 6500000,
    "PSICOLOGIA": 4500000,
    "SALUD ORAL": 3000000,
    "GESTOR COMUNITARIO": 2800000,
    "AUXILIAR ENFERMERIA": 2500000,
    "AUXILIAR VACUNACION": 2500000
}

ACTIVIDAD_META_POR_PERFIL = {
    "MEDICINA": 29,
    "ENFERMERIA": 38,
    "PSICOLOGIA": 34,
    "SALUD ORAL": 23,
    "AUXILIAR VACUNACION": 23,
    "AUXILIAR ENFERMERIA": 23,
    "GESTOR COMUNITARIO": -1
}

TEXTO_DESCUENTO = (
    "Verificados los informes de actividades, soportes y demás evidencias presentadas por el CONTRATISTA, "
    "se evidencia cumplimiento parcial de las obligaciones contractuales correspondientes al periodo evaluado, "
    "conforme a lo establecido en el contrato y en el plan de actividades aprobado.\n\n"
    "En razón a que no se ejecutó la totalidad de las actividades previstas para el periodo evaluado, desde la supervisión "
    "se aplica el descuento proporcional correspondiente sobre el valor de la cuenta de cobro, de acuerdo con las actividades "
    "efectivamente desarrolladas y soportadas.\n\nEn consecuencia, se autoriza el trámite de pago por el valor ajustado.\n\n"
    "Finalmente, se recomienda al CONTRATISTA mantener vigente su afiliación al Sistema General de Seguridad Social Integral "
    "y efectuar oportunamente los aportes correspondientes, en cumplimiento de la normativa vigente y de las obligaciones contractuales asumidas."
)

TEXTO_SIN_DESCUENTO = (
    "Una vez verificados los informes de actividades, soportes allegados y demás evidencias presentadas por el CONTRATISTA, "
    "se constata el cumplimiento de las obligaciones contractuales correspondientes al periodo evaluado, "
    "conforme a lo establecido en el contrato y en el plan de actividades aprobado para su ejecución.\n\n"
    "En consecuencia, desde la supervisión se conceptúa favorablemente el cumplimiento de las actividades desarrolladas y se autoriza "
    "el trámite de pago de la cuenta de cobro presentada, por encontrarse acorde con lo pactado contractual y debidamente soportada.\n\n"
    "No obstante, se recomienda al CONTRATISTA mantener vigente su afiliación a las administradoras del Sistema General de Seguridad Social Integral, "
    "así como continuar efectuando de manera oportuna los aportes correspondientes, en cumplimiento de lo dispuesto en la normativa vigente aplicable "
    "y de las obligaciones contractuales asumidas."
)


class GeneradorPDF:
    def __init__(self, db: Session, templates: Jinja2Templates):
        self.db = db
        self.templates = templates

    def _obtener_logo_b64(self):
        logo_path = os.path.join("static", "logo_left.png")
        if os.path.exists(logo_path):
            with open(logo_path, "rb") as img_file:
                return "data:image/png;base64," + base64.b64encode(img_file.read()).decode('utf-8')
        return ""

    def _normalizar_perfil(self, perfil_raw: str) -> str:
        if not perfil_raw: return ""
        p = str(perfil_raw).strip().upper()
        p = p.replace('Í', 'I').replace('Ó', 'O').replace('É', 'E').replace('Á', 'A')

        if "MEDICIN" in p or "MEDICO" in p:
            return "MEDICINA"
        elif "ENFERMERIA" in p and "AUX" not in p:
            return "ENFERMERIA"
        elif "PSICOLOGIA" in p:
            return "PSICOLOGIA"
        elif "SALUD ORAL" in p or "ODONTOLOG" in p:
            return "SALUD ORAL"
        elif "AUXILIAR DE ENFERMERIA" in p or "AUXILIAR EN ENFERMERIA" in p or "AUXILIAR ENFERMERIA" in p:
            return "AUXILIAR ENFERMERIA"
        elif "VACUNACION" in p:
            return "AUXILIAR VACUNACION"
        elif "GESTOR" in p:
            return "GESTOR COMUNITARIO"
        return p

        # --- NUEVO: TRADUCTOR DE FECHAS A ESPAÑOL ---

    def _formatear_fecha_es(self, fecha_raw):
        if not fecha_raw: return ""
        try:
            if isinstance(fecha_raw, str):
                d = datetime.strptime(fecha_raw, '%Y-%m-%d')
            else:
                d = fecha_raw
            meses = ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio', 'agosto', 'septiembre', 'octubre',
                     'noviembre', 'diciembre']
            return f"{d.strftime('%d')} de {meses[d.month - 1]} de {d.strftime('%Y')}"
        except:
            return str(fecha_raw)

    def _preparar_datos_informe(self, pago: DBPago):
        c = pago.contrato
        contratista = c.contratista

        # 1. TEXTO DINÁMICO DE OBSERVACIONES BASADO EN PERIODO_DESDE Y PERIODO_HASTA
        desde_str = self._formatear_fecha_es(pago.periodo_desde)
        hasta_str = self._formatear_fecha_es(pago.periodo_hasta)
        periodo_texto = f"comprendido entre el {desde_str} y el {hasta_str}" if desde_str and hasta_str else "evaluado"

        texto_descuento_dinamico = (
            f"Verificados los informes de actividades, soportes y demás evidencias presentadas por el CONTRATISTA, "
            f"se evidencia cumplimiento parcial de las obligaciones contractuales correspondientes al periodo {periodo_texto}, "
            f"conforme a lo establecido en el contrato y en el plan de actividades aprobado.\n\n"
            "En razón a que no se ejecutó la totalidad de las actividades previstas para el periodo evaluado, desde la supervisión "
            "se aplica el descuento proporcional correspondiente sobre el valor de la cuenta de cobro, de acuerdo con las actividades "
            "efectivamente desarrolladas y soportadas.\n\nEn consecuencia, se autoriza el trámite de pago por el valor ajustado.\n\n"
            "Finalmente, se recomienda al CONTRATISTA mantener vigente su afiliación al Sistema General de Seguridad Social Integral "
            "y efectuar oportunamente los aportes correspondientes, en cumplimiento de la normativa vigente y de las obligaciones contractuales asumidas."
        )

        texto_sin_descuento_dinamico = (
            f"Una vez verificados los informes de actividades, soportes allegados y demás evidencias presentadas por el CONTRATISTA, "
            f"se constata el cumplimiento de las obligaciones contractuales correspondientes al periodo {periodo_texto}, "
            f"conforme a lo establecido en el contrato y en el plan de actividades aprobado para su ejecución.\n\n"
            "En consecuencia, desde la supervisión se conceptúa favorablemente el cumplimiento de las actividades desarrolladas y se autoriza "
            "el trámite de pago de la cuenta de cobro presentada, por encontrarse acorde con lo pactado contractual y debidamente soportada.\n\n"
            "No obstante, se recomienda al CONTRATISTA mantener vigente su afiliación a las administradoras del Sistema General de Seguridad Social Integral, "
            "así como continuar efectuando de manera oportuna los aportes correspondientes, en cumplimiento de lo dispuesto en la normativa vigente aplicable "
            "y de las obligaciones contractuales asumidas."
        )

        # 2. LÓGICA DE FIRMAS Y VALORES
        valor_base = c.valor_final if c.valor_final else c.valor_total
        causado_hasta_hoy = sum((pg.valor_a_pagar or 0) for pg in c.pagos if pg.numero_pago <= pago.numero_pago)
        saldo_a_pagar = valor_base - causado_hasta_hoy
        valor_pagado_anterior = sum((pg.valor_a_pagar or 0) for pg in c.pagos if pg.numero_pago < pago.numero_pago)

        supervisores = str(c.supervisor or "")
        firmas = [f.strip() for f in supervisores.replace('#', '-').split('-') if f.strip()]
        if not firmas: firmas = [supervisores]

        # 3. LÓGICA DE LA FECHA ESPECÍFICA "DADO EN..."
        fecha_firma_raw = getattr(pago, 'fecha_firma', None)
        if fecha_firma_raw:
            try:
                hoy = datetime.strptime(fecha_firma_raw, '%Y-%m-%d') if isinstance(fecha_firma_raw,
                                                                                   str) else fecha_firma_raw
            except:
                hoy = datetime.now()
        else:
            # Si dejaron el campo vacío, usamos HOY como respaldo
            hoy = datetime.now()

        meses_espanol = ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio', 'agosto', 'septiembre',
                         'octubre', 'noviembre', 'diciembre']

        # Limpiar texto del perfil
        perfil_db = str(c.perfil or "")
        perfil_clean = self._normalizar_perfil(perfil_db)
        actividades_texto = ACTIVIDADES_POR_PERFIL.get(perfil_clean,
                                                       [f"Actividades según contrato (Perfil detectado: {perfil_db})"])

        honorario_esperado = HONORARIOS_POR_PERFIL.get(perfil_clean, 0)
        indice_meta = ACTIVIDAD_META_POR_PERFIL.get(perfil_clean, -1)
        valor_a_pagar_actual = float(pago.valor_a_pagar or 0)

        cumple_todo = True
        if honorario_esperado > 0 and valor_a_pagar_actual < honorario_esperado:
            cumple_todo = False

        actividades_finales = []
        for i, act_desc in enumerate(actividades_texto):
            cumple_esta_actividad = True
            if not cumple_todo and i == indice_meta:
                cumple_esta_actividad = False

            actividades_finales.append({
                "descripcion": act_desc,
                "cumple": cumple_esta_actividad
            })

        observaciones_db = str(pago.observaciones or "").strip()
        if not observaciones_db:
            observacion_final = texto_descuento_dinamico if not cumple_todo else texto_sin_descuento_dinamico
        else:
            observacion_final = observaciones_db

        informe = {
            "tipo_informe": pago.tipo_informe or "PARCIAL",
            "numero_contrato": c.numero_contrato,
            "periodo_desde": pago.periodo_desde,
            "periodo_hasta": pago.periodo_hasta,
            "contratante": "EMPRESA SOCIAL DEL ESTADO NORTE 3 E.S.E.",
            "contratista": contratista.nombre,
            "identificacion": contratista.identificacion,
            "lugar_expedicion": contratista.expedida_en,
            "telefono": contratista.telefono,
            "direccion": contratista.direccion,
            "tipo_persona": contratista.tipo_persona or "NATURAL",
            "codigo_ciiu": c.codigo_ciiu,
            "supervisores_nombres": c.supervisor,
            "supervisores_niveles": c.nivel_prof_supervisor or "N/A",
            "interventor": c.interventor or "N/A",
            "cdp": c.cdp,
            "crp": c.crp,
            "imputacion": c.imputacion,
            "valor_contrato": c.valor_total,
            "fecha_inicio": c.fecha_inicio,
            "fecha_fin": c.fecha_terminacion,
            "tiempo_adicion": c.tiempo_adicion or "N/A",
            "valor_final": c.valor_final or c.valor_total,
            "forma_pago": c.forma_pago,
            "numero_pago": pago.numero_pago,
            "valor_a_pagar": valor_a_pagar_actual,
            "otro_si": pago.otro_si or 0,
            "valor_pagado": valor_pagado_anterior,
            "saldo_a_pagar": saldo_a_pagar,
            "ibc": pago.ibc or 0,
            "periodo_cotizado": pago.periodo_cotizado,
            "eps_nombre": pago.eps_nombre,
            "eps_valor": pago.eps_valor or 0,
            "arl_nombre": pago.arl_nombre,
            "arl_valor": pago.arl_valor or 0,
            "afp_nombre": pago.afp_nombre,
            "afp_valor": pago.afp_valor or 0,
            "sena_valor": pago.sena_valor or 0,
            "icbf_valor": pago.icbf_valor or 0,
            "ccf_valor": pago.ccf_valor or 0,
            "total_planilla": pago.valor_total_planilla or 0,
            "planilla_no": pago.planilla_no,
            "retefuente": (str(pago.anexa_cert).upper() == 'SI') if pago.anexa_cert else False,
            "objeto_contrato": c.objeto,
            "observaciones": observacion_final,
            "folios": pago.folios or '0',
            "dia_firma": hoy.strftime('%d'),  # <-- La fecha exacta que seleccionaste
            "mes_firma": meses_espanol[hoy.month - 1],  # <-- Traducida
            "anio_firma": hoy.strftime('%Y')
        }

        return informe, actividades_finales, firmas

    async def _render_html_to_pdf(self, html_content: str) -> bytes:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            await page.set_content(html_content)
            await page.wait_for_load_state("networkidle")

            pdf_bytes = await page.pdf(
                format="Letter",
                print_background=True,
                margin={"top": "0.3in", "right": "0.3in", "bottom": "0.3in", "left": "0.3in"}
            )
            await browser.close()
            return pdf_bytes

    async def generar_pdf_pago_unico(self, pago_id: int) -> tuple[bytes, str]:
        pago = self.db.query(DBPago).filter(DBPago.id == pago_id).first()
        if not pago: return None, None

        informe, actividades, firmas = self._preparar_datos_informe(pago)
        anexos = ["Cuenta de cobro", "Informe de actividades y anexos", "Planilla de pago de Seguridad Social",
                  "Certificado de ARL"]

        html_content = self.templates.get_template("imprimir_supervision.html").render(
            informe=informe,
            actividades=actividades,
            anexos=anexos,
            firmas=firmas,
            logo_b64=self._obtener_logo_b64()
        )

        pdf_bytes = await self._render_html_to_pdf(html_content)
        nombre_archivo = f"Supervision_Contrato_{informe['numero_contrato']}_Pago_{informe['numero_pago']}.pdf"
        nombre_limpio = re.sub(r'[\\/*?:"<>|]', '_', nombre_archivo)
        return pdf_bytes, nombre_limpio

    async def generar_zip_contratista(self, identificacion: str) -> io.BytesIO:
        pagos = self.db.query(DBPago).join(DBPago.contrato).filter(
            DBPago.contrato.has(contratista_id=identificacion)
        ).all()

        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
            for pago in pagos:
                pdf_bytes, nombre_archivo = await self.generar_pdf_pago_unico(pago.id)
                if pdf_bytes:
                    zip_file.writestr(nombre_archivo, pdf_bytes)

        zip_buffer.seek(0)
        return zip_buffer