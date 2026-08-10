"""추이/브레이크다운 답변에 곁들이는 차트.

단일 지표를 시간(추이) 또는 범주(법인/세부계정 브레이크다운)로 보여주는
것이므로 항상 값이 하나뿐인 단일 시리즈 차트다. 그래서 범례 없이 하나의
파란색(연결결산 데이터에는 없는, 데이터 시각화용 강조색)만 사용하고,
얇은 선/막대와 은은한 격자선, 툴팁으로 정보를 보여준다.
"""

import altair as alt
import pandas as pd

BLUE = "#2a78d6"
GRID_COLOR = "#e1e0d9"
AXIS_COLOR = "#c3c2b7"
MUTED = "#898781"


def trend_line_chart(rows: list, label: str, unit: str) -> alt.Chart:
    df = pd.DataFrame(rows)
    df["분기"] = df.apply(lambda r: f"{r['year']}.{r['quarter']}Q", axis=1)

    axis_style = dict(labelColor=MUTED, titleColor=MUTED, domainColor=AXIS_COLOR, gridColor=GRID_COLOR)

    base = alt.Chart(df).encode(
        x=alt.X("분기:N", sort=None, title="분기", axis=alt.Axis(**axis_style)),
        y=alt.Y("amount:Q", title=f"{label} ({unit})", axis=alt.Axis(**axis_style)),
        tooltip=[
            alt.Tooltip("분기:N", title="분기"),
            alt.Tooltip("amount:Q", title=label, format=",.0f"),
        ],
    )
    line = base.mark_line(color=BLUE, strokeWidth=2)
    points = base.mark_circle(color=BLUE, size=50)
    return (line + points).properties(height=260).configure_view(strokeWidth=0)


def breakdown_bar_chart(rows: list, label: str, unit: str) -> alt.Chart:
    df = pd.DataFrame(rows)
    axis_style_x = dict(labelColor=MUTED, titleColor=MUTED, domainColor=AXIS_COLOR, gridColor=GRID_COLOR)
    axis_style_y = dict(labelColor=MUTED, domainColor=AXIS_COLOR)

    chart = alt.Chart(df).mark_bar(color=BLUE, cornerRadiusEnd=3).encode(
        x=alt.X("amount:Q", title=f"{label} ({unit})", axis=alt.Axis(**axis_style_x)),
        y=alt.Y("label:N", sort="-x", title=None, axis=alt.Axis(**axis_style_y)),
        tooltip=[
            alt.Tooltip("label:N", title="구분"),
            alt.Tooltip("amount:Q", title=label, format=",.0f"),
        ],
    )
    height = max(120, 22 * len(df))
    return chart.properties(height=height).configure_view(strokeWidth=0)
