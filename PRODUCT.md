# Product Identity & Intent

Define a intenção, a voz da marca e o público do **Diário Oficial Scraper**.

## Users
* **Principal:** Auditor técnico (você), focado em extrair dados rápidos e precisos das publicações.
* **Secundário:** Colaboradores de cobertura (durante férias), que necessitam de um fluxo visualmente intuitivo, sem ambiguidades de controle.

## Register & Tone
* **Registro:** Product-first. O design existe unicamente para dar legibilidade, contraste e clareza aos dados.
* **Tom de Voz:** Clínico, preciso, calmo e utilitário. Sem artifícios estéticos supérfluos ou textos de marketing/hype.

## Aesthetic Direction
* **Tema Principal:** Dark-Mode Industrial/Sóbrio (grafite/carvão em vez de azul espacial clássico).
* **Paleta de Cores:** Foco em status. Cada tipo de ato do diário oficial tem uma cor de destaque perceptiva em OKLCH (com alto contraste sobre fundo escuro).
* **Tipografia:** 
  * Títulos e Indicadores Rápidos: **Space Grotesk** (geométrica e limpa).
  * Texto de Snippets/Card Body: **Instrument Sans** (humanista, legível).
  * Hashes, Datas, Valores e Logs: **JetBrains Mono** (largura fixa para precisão matemática).

## Anti-References & Avoided Patterns
* **Sem AI Slop:** Nada de gradientes roxos/azuis intensos no fundo ou nos botões.
* **Sem Cardocalypse:** Evitar cards dentro de cards com múltiplas bordas redundantes. Usar separações tipográficas e grids limpos.
* **Sem Contraste Pobre:** Nada de texto cinza-escuro em fundo preto. Todos os textos secundários devem ser totalmente legíveis.
* **Sem Arredondamentos Excessivos:** Manter cantos limpos e profissionais (`border-radius` máximo de `8px`).
