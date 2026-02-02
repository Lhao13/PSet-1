# PST#1

**Instrucciones:**

Construir un pipeline de datos de backfill histórico que extraiga información de QuickBooks
Online (QBO) para las entidades Invoices, Customers y Items, y la deposite en Postgres dentro
de un esquema raw.
La orquestación se realizará con Mage, el despliegue con Docker Compose, y todas las
credenciales/tokens deberán gestionarse mediante Mage Secrets.

---

# Arquitectura

## Descripción

La solución sigue una arquitectura **EL (Extract → Load)** desacoplada:

1. Mage ejecuta pipelines batch mediante un trigger one-time.
2. Se autentica contra QuickBooks Online.
3. Se extraen entidades mediante queries SQL-like de QBO.
4. Los datos se cargan en PostgreSQL bajo el esquema `raw`.
5. Se registran métricas, logs y metadata de extracción.

---

## Diagrama de arquitectura



#  Levantar el proyecto

## 1. Clonar el repositorio

```bash
git clone https://github.com/Lhao13/PSet-1
cd <repo>
```

## 2. Levantar contenedores

```bash
docker compose up -d
```

Verificar:

```bash
docker ps
```

Deberías ver contenedores similares a:

- mage
- pgadmin
- postgres

## 3.Acceder a Mage

```bash
http://localhost:6789
```
Los triggers se pueden encontra al lado izquierdo de la pantalla para corre los pipelines

#  2.Gestión de secretos


| Secret Name | Propósito | Rotación | Responsable |
|------------|-------------|------------|-------------|
| `QBO_REALM_ID` | Identificador de la empresa en QBO | Baja (solo cambia al migrar tenant) | Data Platform |
| `QBO_REFRESH_TOKEN` | Token Refresh de QuickBooks | 100 dias | API |
| `QBO_CLIENT_SECRET` | Token Client de QuickBooks | nunca | API |
| `QBO_CLIENT_ID` | Token client de QuickBooks | nunca | API |
| `PG_HOST` | Host de PostgreSQL | Baja | Infra |
| `PG_PORT` | Puerto DB | Baja | Infra |
| `PG_DB` | Nombre DB | Baja | Infra |
| `PG_USER` | Usuario DB | Media | Infra |
| `PG_PASSWORD` | Password DB | Alta | Infra/Security |

---

# 3.Pipelines Backfill

Se implementaron tres pipelines, los tres pipelines usan una arquitectura similar, los bloques de autenticacion y de fechas se reutilizan en los pipelines por facilidad:

- qb_customers_backfill
- qb_items_backfill
- qb_invoices_backfill

## Parámetros para todos los pipelines

| Parámetro | Descripción |
|------------|-------------|
| `fecha_inicio` | Inicio del rango histórico (UTC) |
| `fecha_fin` | Fin del rango histórico (UTC) |

---

## Segmentación

Los pipelines dividen el rango en ventanas de:
30 días por segmento

### Ventajas

- Reduce riesgo de timeouts  
- Evita rate limits  
- Permite reanudación parcial 

## Límites y paginación

QuickBooks usa:

STARTPOSITION

MAXRESULTS (100 recomendado)

Se itera hasta que:
records < page_size


---

## Reintentos (Retry + Backoff)

**Configuración dentro de los bloques:**

- Retries: **5**
- Backoff exponencial
- Status codes: 429, 500, 502, 503, 504

### Protege contra:

- Rate limiting  
- Fallas temporales de red  
- Saturación del API  

---

## Runbook (operación)

### Si falla un pipeline:

1. Revisar logs en Mage o contenedor (los logs dentro de mages no suelen mostrar todas las operaciones, pero dentro de los logs del contenedor de mages se puede ver todas las operaciones).
2. Identificar el segmento fallido (mediante los logs).
3. Reejecutar solo ese rango (apartir de las variables de fechas definidas).

No es necesario repetir todo el backfill.

---

# Trigger One-Time

Los backfills deben ejecutarse con trigger manual o programado una sola vez. Estos estan en la pantalla principal de mages. Se establece un fecha tentativa de ejecucion

---

## Política post-ejecución

Después de completar el backfill:

- Se deshabilitar trigger  
- Evitar reprocesamientos accidentales  
- Mantener pipelines solo para recovery  

---

# Esquema RAW

## Tablas

- raw.qb_customers
- raw.qb_items
- raw.qb_invoices

---
## Script SQL

```bash
-- =========================
-- 1. Crear esquema RAW
-- =========================
CREATE SCHEMA IF NOT EXISTS raw;

-- =========================
-- 2. Tabla: Invoices
-- =========================
CREATE TABLE IF NOT EXISTS raw.qb_invoices (
    id TEXT PRIMARY KEY, -- ID de QuickBooks
    payload JSONB NOT NULL, -- Payload completo de la API
    ingested_at_utc TIMESTAMP NOT NULL DEFAULT NOW(),
    extract_window_start_utc TIMESTAMP NOT NULL,
    extract_window_end_utc TIMESTAMP NOT NULL,
    page_number INT,
    page_size INT,
    request_payload JSONB
);

-- =========================
-- 3. Tabla: Customers
-- =========================
CREATE TABLE IF NOT EXISTS raw.qb_customers (
    id TEXT PRIMARY KEY,
    payload JSONB NOT NULL,
    ingested_at_utc TIMESTAMP NOT NULL DEFAULT NOW(),
    extract_window_start_utc TIMESTAMP NOT NULL,
    extract_window_end_utc TIMESTAMP NOT NULL,
    page_number INT,
    page_size INT,
    request_payload JSONB
);

-- =========================
-- 4. Tabla: Items
-- =========================
CREATE TABLE IF NOT EXISTS raw.qb_items (
    id TEXT PRIMARY KEY,
    payload JSONB NOT NULL,
    ingested_at_utc TIMESTAMP NOT NULL DEFAULT NOW(),
    extract_window_start_utc TIMESTAMP NOT NULL,
    extract_window_end_utc TIMESTAMP NOT NULL,
    page_number INT,
    page_size INT,
    request_payload JSONB
);
```
---
### Garantiza:

- No duplicados, especialmente en clave primaria

- Reprocesamiento seguro

- Consistencia
- Protege contra datos nulos
- Todas las tablas permiten ingresar los metadatos estipulados en el trabajo como se observa en el script

#  Validaciones y Volumetría

## Qué validar

### Conteos

Comparar:

``` bash
QBO count vs RAW count
``` 
De esta el codigo valida que los datos que tiene estan completos con los que proporciona la API

---

### Duplicados
En caso de exitir duplicados el codigo lo unico que hace es update a los datos, se devuelven el valor de valores actulizados en los logs

``` bash
 ON CONFLICT (id)
        DO UPDATE SET
            payload = EXCLUDED.payload,
            ingested_at_utc = EXCLUDED.ingested_at_utc,
            extract_window_start_utc = EXCLUDED.extract_window_start_utc,
            extract_window_end_utc = EXCLUDED.extract_window_end_utc,
            page_number = EXCLUDED.page_number,
            page_size = EXCLUDED.page_size,
            request_payload = EXCLUDED.request_payload
        RETURNING (xmax = 0) AS inserted;
``` 


---

## Interpretacion de conteos

| Resultado | Significado | 
|------------|-------------|
| Conteos similares| Pipeline sano
| Menor volumen | Segmento faltante | 
| Duplicados| Error de idempotencia | 
| Sin datos nuevos | Trigger mal configurado | 


---
# Troubleshooting

## Auth falla

Error: 401 / 403
Comentario: tuve varias fallas con la conexion de la API durante algunos test de QBO, donde en el mismo entorno depruebas no me devolvian nada o me daban error. No estoy seguro porque paso esto, pero se soluciono mas adelante

- Causas comunes:

- Token expirado

- Realm incorrecto

## Error de paginacion

Causa común:

``` bash
STARTPOSITION mal calculado
```

Debe incrementar por page_size.

## Problemas de timezone

Siempre usar el time zone dentro de la variables fechas

``` bash
UTC 
``` 


## Permisos / almacenamiento

Si Postgres falla: (jamas tuve problemas con respecto ah esto)

- Revisar credenciales (en secrets)

- Revisar red Docker

- Verificar espacio en disco

