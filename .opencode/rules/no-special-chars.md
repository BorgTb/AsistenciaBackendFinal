# No usar caracteres especiales no estandar

Al escribir cualquier texto en espanol (documentos .tex, mensajes, comentarios en codigo), debes usar exclusivamente caracteres ASCII o caracteres UTF-8 estandar del espanol. En particular:

- **Guiones**: Usa solo el guion medio `-` (U+002D). NO uses guion largo `—` (U+2014, em dash) ni guion corto `–` (U+2013, en dash).
- **Comillas**: Usa solo comillas rectas `"` y `'`. NO uses comillas curvas `""`, `''`, ni comillas latinas `<< >>`, `" "`.
- **Puntos suspensivos**: Usa tres puntos seguidos `...`. NO uses el caracter unico de puntos suspensivos `…` (U+2026).
- **Acentos y enies**: Son correctos y necesarios los caracteres propios del espanol: `á`, `é`, `í`, `ó`, `ú`, `ñ`, `ü`, y sus mayusculas.
- **Separadores**: En listas y enumeraciones usa solo el guion normal `-`. No uses viñetas especiales como `•`.
- **Simbolos matematicos**: Usa solo simbolos LaTeX estandar ($\ge$, $\le$, $\neq$, etc.). No uses simbolos Unicode equivalentes como `≥`, `≤`, `≠` fuera de modo matematico.

Esto aplica a todo el contenido textual generado, incluyendo archivos .tex, mensajes al usuario, documentacion, comentarios y commit messages.
