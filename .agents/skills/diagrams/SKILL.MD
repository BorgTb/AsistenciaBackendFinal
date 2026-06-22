---
name: sequence-diagram
description: >
  Genera diagramas de secuencia UML como SVG inline en el chat. Usar siempre
  que el usuario pida un diagrama de secuencia, flujo de mensajes entre
  componentes, interacción entre actores/servicios, o cualquier diagrama
  que muestre quién llama a quién y en qué orden. También usar cuando el
  usuario pida visualizar una API, un protocolo, un flujo de autenticación,
  un proceso con múltiples partes, o cuando diga frases como "cómo se
  comunican", "flujo de llamadas", "quién llama a quién", "interacción entre".
  Aplicar igualmente si el usuario pide actualizar o mejorar un diagrama
  de secuencia existente.
---

# Skill: Diagrama de secuencia SVG

Genera diagramas de secuencia UML limpios y legibles como SVG inline.
El objetivo es que el texto nunca se solape, los mensajes queden alineados
y el diagrama sea escaneable de arriba a abajo.

---

## 1. Estructura del SVG

```
viewBox="0 0 680 H"   ← siempre 680 de ancho, H calculado al final
width="100%"
role="img"            ← accesibilidad
```

Elementos obligatorios justo tras `<svg>`:
```svg
<title>Descripción breve del diagrama</title>
<desc>Descripción extendida para lectores de pantalla</desc>
<defs>…marker arrow…</defs>
```

---

## 2. Layout de participantes

### Reglas de posicionamiento

- Calcular el ancho de cada cabecera: `chars × 8 + 32px de padding`
- Distribuir los participantes con espacio uniforme a lo largo de 680px
- Fórmula para N participantes:
  - `gap = (640 - suma_anchos) / (N - 1)`
  - `x[0] = 20`, `x[i] = x[i-1] + ancho[i-1] + gap`
- El centro de cada participante (`cx`) es `x[i] + ancho[i] / 2`
- Guardar todos los `cx` como constantes antes de dibujar

### Cabeceras

Estilo académico: fondo blanco, borde negro, texto negro. Sin colores.

```svg
<g>
  <rect x="{x}" y="20" width="{w}" height="40" rx="4"
        fill="var(--color-background-primary)"
        stroke="var(--color-text-primary)" stroke-width="1"/>
  <text class="th" x="{cx}" y="40" text-anchor="middle"
        dominant-baseline="central"
        style="fill:var(--color-text-primary)">{Nombre}</text>
</g>
```

### Líneas de vida

```svg
<line x1="{cx}" y1="60" x2="{cx}" y2="{H-10}"
      stroke="var(--color-text-primary)" stroke-width="0.8"
      stroke-dasharray="4 4"/>
```

---

## 3. Mensajes

### Espaciado vertical

- Primera fila de mensajes: `y_start = 100`
- Entre filas: `row_gap = 50px`  ← esto es lo más importante para que no se solapen
- `y[i] = y_start + i × row_gap`

**NUNCA** asignar dos mensajes a la misma `y`. Siempre incrementar.

### Flecha de llamada (línea sólida)

```svg
<!-- Flecha de izquierda a derecha -->
<line x1="{cx_origen + 4}" y1="{y}" x2="{cx_destino - 4}" y2="{y}"
      stroke="var(--color-text-primary)" stroke-width="1.2"
      marker-end="url(#arrow)" fill="none"/>

<!-- Flecha de derecha a izquierda -->
<line x1="{cx_origen - 4}" y1="{y}" x2="{cx_destino + 4}" y2="{y}"
      stroke="var(--color-text-primary)" stroke-width="1.2"
      marker-end="url(#arrow)" fill="none"/>
```

### Flecha de retorno (línea punteada)

```svg
<line x1="{cx_origen ± 4}" y1="{y}" x2="{cx_destino ∓ 4}" y2="{y}"
      stroke="var(--color-text-primary)" stroke-width="0.8"
      stroke-dasharray="5 3" marker-end="url(#arrow)" fill="none"/>
```

### Etiqueta del mensaje — regla crítica de posición

La etiqueta va **encima** de la flecha, centrada entre los dos participantes.
Siempre con `fill` explícito negro para garantizar legibilidad académica:

```svg
<text class="ts"
      x="{(cx_origen + cx_destino) / 2}"
      y="{y - 8}"
      text-anchor="middle"
      style="fill:var(--color-text-primary)">{texto del mensaje}</text>
```

- `y - 8`: siempre 8px por encima de la línea
- `text-anchor="middle"`: siempre centrado
- **Nunca** poner la etiqueta debajo de la flecha
- Si el texto mide más de `(|cx_destino - cx_origen| - 20)` píxeles → acortarlo

### Estimación de ancho de texto

`ancho ≈ chars × 7px` (clase `ts`, 12px)

Si el texto no cabe entre los dos participantes: abreviarlo o dividir en dos mensajes.

---

## 4. Separadores de sección

Cuando el flujo tiene fases distintas (ej: login / checkout):

```svg
<!-- Línea separadora -->
<line x1="20" y1="{y_sep}" x2="660" y2="{y_sep}"
      stroke="var(--color-border-tertiary)" stroke-width="0.5"
      stroke-dasharray="2 3"/>
<!-- Etiqueta del separador — sobre la línea, a la izquierda -->
<text class="ts" x="340" y="{y_sep - 6}" text-anchor="middle"
      style="fill:var(--color-text-tertiary)">— {Nombre de la fase} —</text>
```

Reservar `40px` de espacio vertical para cada separador.

---

## 5. Marcador de flecha (defs)

Siempre incluir exactamente este marcador:

```svg
<defs>
  <marker id="arrow" viewBox="0 0 10 10" refX="8" refY="5"
          markerWidth="6" markerHeight="6" orient="auto-start-reverse">
    <path d="M2 1L8 5L2 9" fill="none" stroke="context-stroke"
          stroke-width="1.5" stroke-linecap="round"
          stroke-linejoin="round"/>
  </marker>
</defs>
```

---

## 6. Cálculo de altura del viewBox

```
H = y_ultimo_mensaje + 50
```

Verificar: ningún elemento supera `y = H - 10`.

---

## 7. Paleta académica (blanco y negro)

El diagrama es monocromático. Sin colores de relleno en cabeceras ni elementos.

| Elemento              | Fill                              | Stroke                         | Stroke-width |
|-----------------------|-----------------------------------|--------------------------------|--------------|
| Cabecera (rect)       | `var(--color-background-primary)` | `var(--color-text-primary)`    | `1`          |
| Línea de vida         | —                                 | `var(--color-text-primary)`    | `0.8`        |
| Flecha llamada        | —                                 | `var(--color-text-primary)`    | `1.2`        |
| Flecha retorno        | —                                 | `var(--color-text-primary)`    | `0.8`        |
| Separador de sección  | —                                 | `var(--color-text-primary)`    | `0.5`        |
| Todo el texto         | `var(--color-text-primary)`       | —                              | —            |

**No usar** `c-purple`, `c-teal`, `c-blue`, `c-amber` ni ninguna clase de color.
**No usar** `var(--color-text-secondary)` ni `var(--color-text-tertiary)` para flechas o texto.
Siempre `style="fill:var(--color-text-primary)"` en los `<text>` para forzar negro en modo claro y blanco en modo oscuro.

---

## 8. Checklist antes de emitir el SVG

- [ ] Todos los `cx` calculados y consistentes entre cabecera, línea de vida y mensajes
- [ ] Ningún par de etiquetas de mensaje comparte la misma `y`
- [ ] Todas las etiquetas están en `y - 8` (encima de la flecha)
- [ ] `text-anchor="middle"` en todas las etiquetas
- [ ] El texto más largo de cada etiqueta cabe entre sus dos participantes
- [ ] `viewBox` height = `y_ultimo + 50`
- [ ] Líneas de vida llegan hasta al menos el último mensaje
- [ ] `fill="none"` en todas las líneas/paths de flechas

---

## 9. Ejemplo mínimo (3 participantes, 4 mensajes)

```svg
<svg width="100%" viewBox="0 0 680 280" role="img"
     xmlns="http://www.w3.org/2000/svg">
  <title>Ejemplo: autenticación</title>
  <desc>Flujo de login entre Cliente, API y Base de datos</desc>
  <defs>
    <marker id="arrow" viewBox="0 0 10 10" refX="8" refY="5"
            markerWidth="6" markerHeight="6" orient="auto-start-reverse">
      <path d="M2 1L8 5L2 9" fill="none" stroke="context-stroke"
            stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
    </marker>
  </defs>

  <!-- cx: Cliente=105, API=340, DB=575 -->

  <!-- Cabeceras: fondo blanco, borde negro -->
  <rect x="50" y="20" width="110" height="40" rx="4"
        fill="var(--color-background-primary)"
        stroke="var(--color-text-primary)" stroke-width="1"/>
  <text class="th" x="105" y="40" text-anchor="middle"
        dominant-baseline="central"
        style="fill:var(--color-text-primary)">Cliente</text>

  <rect x="285" y="20" width="110" height="40" rx="4"
        fill="var(--color-background-primary)"
        stroke="var(--color-text-primary)" stroke-width="1"/>
  <text class="th" x="340" y="40" text-anchor="middle"
        dominant-baseline="central"
        style="fill:var(--color-text-primary)">API</text>

  <rect x="520" y="20" width="110" height="40" rx="4"
        fill="var(--color-background-primary)"
        stroke="var(--color-text-primary)" stroke-width="1"/>
  <text class="th" x="575" y="40" text-anchor="middle"
        dominant-baseline="central"
        style="fill:var(--color-text-primary)">Base de datos</text>

  <!-- Líneas de vida -->
  <line x1="105" y1="60" x2="105" y2="270"
        stroke="var(--color-text-primary)" stroke-width="0.8"
        stroke-dasharray="4 4"/>
  <line x1="340" y1="60" x2="340" y2="270"
        stroke="var(--color-text-primary)" stroke-width="0.8"
        stroke-dasharray="4 4"/>
  <line x1="575" y1="60" x2="575" y2="270"
        stroke="var(--color-text-primary)" stroke-width="0.8"
        stroke-dasharray="4 4"/>

  <!-- Mensaje 1: y=100 (llamada, línea sólida) -->
  <text class="ts" x="222" y="92" text-anchor="middle"
        style="fill:var(--color-text-primary)">POST /login</text>
  <line x1="109" y1="100" x2="336" y2="100"
        stroke="var(--color-text-primary)" stroke-width="1.2"
        marker-end="url(#arrow)" fill="none"/>

  <!-- Mensaje 2: y=150 (llamada) -->
  <text class="ts" x="457" y="142" text-anchor="middle"
        style="fill:var(--color-text-primary)">SELECT usuario</text>
  <line x1="344" y1="150" x2="571" y2="150"
        stroke="var(--color-text-primary)" stroke-width="1.2"
        marker-end="url(#arrow)" fill="none"/>

  <!-- Mensaje 3: y=200 (retorno, línea punteada) -->
  <text class="ts" x="457" y="192" text-anchor="middle"
        style="fill:var(--color-text-primary)">usuario encontrado</text>
  <line x1="571" y1="200" x2="344" y2="200"
        stroke="var(--color-text-primary)" stroke-width="0.8"
        stroke-dasharray="5 3" marker-end="url(#arrow)" fill="none"/>

  <!-- Mensaje 4: y=250 (retorno) -->
  <text class="ts" x="222" y="242" text-anchor="middle"
        style="fill:var(--color-text-primary)">200 OK · token JWT</text>
  <line x1="336" y1="250" x2="109" y2="250"
        stroke="var(--color-text-primary)" stroke-width="0.8"
        stroke-dasharray="5 3" marker-end="url(#arrow)" fill="none"/>
</svg>
```

---

## 10. Errores comunes a evitar

| Error                              | Corrección                                      |
|------------------------------------|-------------------------------------------------|
| Etiqueta debajo de la flecha       | Siempre `y_label = y_arrow - 8`                 |
| Etiquetas solapadas                | `row_gap` mínimo de 50px entre filas            |
| Texto que sale del viewBox         | Recortar texto o aumentar el viewBox width      |
| cx inconsistente                   | Definir todos los cx al inicio como constantes  |
| Líneas de vida muy cortas          | Extender hasta `H - 10`                         |
| Flechas que tocan el borde del box | Dejar `±4px` de margen desde el cx              |
| viewBox muy pequeño                | `H = y_ultimo_mensaje + 50`                     |