# Third-Party Notices

Alear030's own source code is licensed under MIT (see [LICENSE](LICENSE)).
This repository also carries files from third-party projects under their
own licenses, listed below. Those files are not covered by the MIT License.

## GTE Chinese Base (sentence embedding model)

Files under:

```
local_model/iic/nlp_gte_sentence-embedding_chinese-base/
```

(`README.md`, `config.json`, `configuration.json`, `requirements.txt`,
`special_tokens_map.json`, `tokenizer.json`, `tokenizer_config.json`,
`resources/dual-encoder.png`, and the ModelScope metadata files `.mdl`/
`.msc`/`.mv`) are distributed by the upstream model repository, which
declares itself licensed under the Apache License 2.0 (see the `license`
field in that directory's `README.md`).

- Upstream: https://www.modelscope.cn/models/iic/nlp_gte_sentence-embedding_chinese-base
- License: [Apache License 2.0](licenses/Apache-2.0.txt)

The model weight files (`pytorch_model.bin` / `model.safetensors`) are not
tracked in this repository; they are downloaded at runtime from ModelScope
and are governed by the same upstream license.
