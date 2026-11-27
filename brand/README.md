# Logo

CosmosProof uses the Cosmos Semantic mark (a sky-blue planet, a tilted ring and a small green moon) with its own name, "CosmosProof": one word, "Cosmos" in Inter ExtraBold and "Proof" in Inter Medium. Same versions, themes, colors and rules as the Cosmos Semantic logo ([marketing/brand](https://github.com/WiliamRosa/cosmos-semantic-platform/tree/main/marketing/brand)).

| Version | SVG | PNG |
| --- | --- | --- |
| Horizontal (default) | `cosmosproof-horizontal-<theme>.svg` | `png/…-2000w.png`, `png/…-4000w.png` |
| Stacked | `cosmosproof-stacked-<theme>.svg` | `png/…-2000w.png`, `png/…-4000w.png` |
| Mark | `cosmosproof-mark-<theme>.svg` | `png/…-1024.png`, `png/…-2048.png` |
| Icon | `cosmosproof-icon.svg` | `png/…-48.png` to `png/…-2048.png` |
| Avatar | `cosmosproof-avatar.svg` | `png/…-400.png`, `-1024`, `-2048` |

Themes: `dark` (navy or dark backgrounds, the default), `light`, `white`, `black`. Brand background navy `#0b1220`.

Regenerate with Inter's static TTFs (`inter-500.ttf`, `inter-800.ttf`) and Google Chrome:

```bash
uv run --no-project --with uharfbuzz --with fonttools --with playwright \
  python brand/build_logo.py path/to/inter-fonts
```
