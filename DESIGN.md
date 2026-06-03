# Design System Specification

## Palette (OKLCH)

Definição de cores baseada no espaço perceptivo OKLCH para garantir brilho perceptivo uniforme e contraste acessível.

| Token | OKLCH | Visual / Uso |
| :--- | :--- | :--- |
| `--bg-app` | `oklch(14% 0.01 260)` | Fundo da aplicação (grafite escuro) |
| `--bg-panel` | `oklch(18% 0.012 260)` | Fundo de painéis e sidebar (carvão) |
| `--bg-card` | `oklch(22% 0.015 260)` | Fundo dos cards de resultados (ardósia) |
| `--border-subtle` | `oklch(28% 0.015 260)` | Bordas finas de separação |
| `--border-focus` | `oklch(68% 0.16 220)` | Borda ativa de inputs/botões |
| `--text-primary` | `oklch(96% 0.005 260)` | Texto principal (quase branco) |
| `--text-secondary` | `oklch(80% 0.01 260)` | Texto secundário (legível, cinza claro) |
| `--text-muted` | `oklch(62% 0.015 260)` | Metadados e labels menores (cinza médio) |
| `--accent-primary` | `oklch(68% 0.16 220)` | Cor ativa primária (ciano cirúrgico) |
| `--accent-hover` | `oklch(74% 0.14 220)` | Estado hover da cor primária |

### Status Colors (OKLCH)
* **Compra/Contrato:** `oklch(70% 0.18 140)` (Verde folha)
* **Aditamento:** `oklch(75% 0.17 75)` (Laranja quente)
* **Parceria:** `oklch(72% 0.15 190)` (Azul esverdeado/Teal)
* **Doação:** `oklch(68% 0.17 310)` (Ametista)
* **Diversos/Outros:** `oklch(60% 0.02 260)` (Cinza neutro)

---

## Typography

Par de fontes com três propósitos bem delineados:

* **Display & Brand:** `Space Grotesk`
  * Usada para títulos de seções, contadores numéricos de resumo e a marca `DO.Scraper`.
* **Reading & Content:** `Instrument Sans`
  * Usada para o texto corrido de snippets e descrições dos cards.
* **Data & Logs:** `JetBrains Mono`
  * Usada para valores monetários, datas, hashes e a janela de log de execução da raspagem.

### Escala de Tamanhos
* `font-size-xs`: `0.75rem` (12px) - metadados e badges
* `font-size-sm`: `0.875rem` (14px) - texto secundário, inputs, botões secundários
* `font-size-base`: `1rem` (16px) - texto principal
* `font-size-lg`: `1.125rem` (18px) - títulos de cards
* `font-size-xl`: `1.5rem` (24px) - títulos de seções/header
* `font-size-2xl`: `2rem` (32px) - contadores e números de estatísticas

---

## Spacing

Escala estrita de espaçamento (base 4px) para alinhamento horizontal e vertical consistentes.

* `space-xs`: `0.25rem` (4px)
* `space-sm`: `0.5rem` (8px)
* `space-md`: `1rem` (16px)
* `space-lg`: `1.5rem` (24px)
* `space-xl`: `2rem` (32px)

---

## Shapes & Radii

* **Cantos de Inputs & Botões:** `6px` (`border-radius: 0.375rem`) - visual corporativo e limpo.
* **Cantos de Cards & Painéis:** `8px` (`border-radius: 0.5rem`) - cantos ligeiramente arredondados, evitando o aspecto "bubbly/arredondado" genérico de IA.

---

## Motion / Animations

* **Transições Simples (Hover/Foco):** `150ms cubic-bezier(0.4, 0, 0.2, 1)` para cor de fundo e bordas.
* **Micro-animação de Carregamento (Loading):** Barra de progresso linear e suave baseada em `translateX` infinito para sinalizar atividade sem sobrecarga visual.
