PST#1

Construir un pipeline de datos de backfill histórico que extraiga información de QuickBooks
Online (QBO) para las entidades Invoices, Customers y Items, y la deposite en Postgres dentro
de un esquema raw.
La orquestación se realizará con Mage, el despliegue con Docker Compose, y todas las
credenciales/tokens deberán gestionarse mediante Mage Secrets.