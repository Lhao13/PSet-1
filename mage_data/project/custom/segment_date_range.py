from datetime import datetime, timedelta

@custom
def execute(*args, **kwargs):

    fecha_inicio = kwargs.get("fecha_inicio")
    fecha_fin = kwargs.get("fecha_fin")

    if not fecha_inicio or not fecha_fin:
        raise ValueError("fecha_inicio y fecha_fin son requeridas")

    start = datetime.fromisoformat(fecha_inicio.replace("Z", ""))
    end = datetime.fromisoformat(fecha_fin.replace("Z", ""))

    segments = []
    current = start

    while current < end:
        # 30 dias de segmentacion
        next_day = min(current + timedelta(days=30), end)

        segments.append({
            "window_start": current.isoformat() + "Z",
            "window_end": next_day.isoformat() + "Z"
        })

        current = next_day

    print(f"Segments generated: {len(segments)}")

    return segments
