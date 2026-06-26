---
tasks:
- sentence-embedding
widgets:
- version: v1.1.0
  task: sentence-embedding
  inputs:
      - type: text
        name: source_sentence
      - type: text-list
        name: sentences_to_compare
  examples:
      - name: 示例1
        inputs:
          - data:
            - 功和功率的区别
          - data: 
            - 功反映做功多少，功率反映做功快慢。
            - 什么是有功功率和无功功率?无功功率有什么用什么是有功功率和无功功率?无功功率有什么用电力系统中的电源是由发电机产生的三相正弦交流电,在交>流电路中,由电源供给负载的电功率有两种;一种是有功功率,一种是无功功率.
            - 优质解答在物理学中,用电功率表示消耗电能的快慢．电功率用P表示,它的单位是瓦特（Watt）,简称瓦（Wa）符号是W.电流在单位时间内做的功叫做电功率 以灯泡为例,电功率越大,灯泡越亮.灯泡的亮暗由电功率（实际功率）决定,不由通过的电流、电压、电能决定!
      - name: 示例2
        inputs:
          - data:
            - 什么是桥
          - data:
            - 由全国科学技术名词审定委员会审定的科技名词“桥”的定义为：跨越河流、山谷、障碍物或其他交通线而修建的架空通道
            - 桥是一种连接两岸的建筑
            - 转向桥，是指承担转向任务的车桥。一般汽车的前桥是转向桥。四轮转向汽车的前后桥，都是转向桥。
            - 桥梁艺术研究桥梁美学效果的艺术。起源于人类修建桥梁的实践。作为一种建筑，由于功能不同、使用材料有差别，桥梁表现为不同的结构和形式。基本的有拱桥、梁桥和吊桥。
      - name: 示例3
        inputs:
          - data:
            - 福鼎在哪个市
          - data:
            - 福鼎是福建省宁德市福鼎市。
            - 福鼎位于福建省东北部，东南濒东海，水系发达，岛屿星罗棋布。除此之外，福鼎地貌丰富，著名的太姥山就在福鼎辖内，以峰险、石奇、洞幽、雾幻四绝著称于世。
            - 福鼎市人民政府真诚的欢迎国内外朋友前往迷人的太姥山观光、旅游。
            - 福建省福鼎市桐山街道,地处福鼎城区,地理环境优越,三面环山,东临大海,境内水陆交通方便,是福鼎政治、经济、文化、交通中心区。
      - name: 示例4
        inputs:
          - data:
            - 吃完海鲜可以喝牛奶吗?
          - data: 
            - 不可以，早晨喝牛奶不科学
            - 吃了海鲜后是不能再喝牛奶的，因为牛奶中含得有维生素C，如果海鲜喝牛奶一起服用会对人体造成一定的伤害
            - 吃海鲜是不能同时喝牛奶吃水果，这个至少间隔6小时以上才可以。
            - 吃海鲜是不可以吃柠檬的因为其中的维生素C会和海鲜中的矿物质形成砷
model-type:
- bert

domain:
- nlp

frameworks:
- pytorch

backbone:
- transformer

metrics:
- mrr@10
- recall@1000
- ndcg@10

license: Apache License 2.0

language:
- en

tags:
- text representation
- text retrieval
- passage retrieval
- Transformer
- GTE
- 文本相关性
- 文本相似度

---

# GTE中文通用文本表示模型

文本表示是自然语言处理(NLP)领域的核心问题, 其在很多NLP、信息检索的下游任务中发挥着非常重要的作用。近几年, 随着深度学习的发展，尤其是预训练语言模型的出现极大的推动了文本表示技术的效果, 基于预训练语言模型的文本表示模型在学术研究数据、工业实际应用中都明显优于传统的基于统计模型或者浅层神经网络的文本表示模型。这里, 我们主要关注基于预训练语言模型的文本表示。

文本表示示例, 输入一个句子, 输入一个固定维度的连续向量:

- 输入: 吃完海鲜可以喝牛奶吗?
- 输出: [0.27162,-0.66159,0.33031,0.24121,0.46122,...]

文本的向量表示通常可以用于文本聚类、文本相似度计算、文本向量召回等下游任务中。

## 文本表示模型

基于监督数据训练的文本表示模型通常采用Dual Encoder框架, 如下图所示。在Dual Encoder框架中, Query和Document文本通过预训练语言模型编码后, 通常采用预训练语言模型[CLS]位置的向量作为最终的文本向量表示。基于标注数据的标签, 通过计算query-document之间的cosine距离度量两者之间的相关性。

<div align=center><img width="450" height="300" src="./resources/dual-encoder.png" /></div>

GTE-zh模型使用[retromae](https://arxiv.org/abs/2205.12035)初始化训练模型，之后利用两阶段训练方法训练模型：第一阶段利用大规模弱弱监督文本对数据训练模型，第二阶段利用高质量精标文本对数据以及挖掘的难负样本数据训练模型。具体训练方法请参考论文[Towards General Text Embeddings with Multi-stage Contrastive Learning](https://arxiv.org/abs/2308.03281)。

## 使用方式和范围

使用方式:
- 直接推理, 对给定文本计算其对应的文本向量表示，向量维度768

使用范围:
- 本模型可以使用在通用领域的文本向量表示及其下游应用场景, 包括双句文本相似度计算、query&多doc候选的相似度排序

### 如何使用

在ModelScope框架上，提供输入文本(默认最长文本长度为128)，即可以通过简单的Pipeline调用来使用GTE文本向量表示模型。ModelScope封装了统一的接口对外提供单句向量表示、双句文本相似度、多候选相似度计算功能

#### 代码示例
```python
from modelscope.models import Model
from modelscope.pipelines import pipeline
from modelscope.utils.constant import Tasks

model_id = "iic/nlp_gte_sentence-embedding_chinese-base"
pipeline_se = pipeline(Tasks.sentence_embedding,
                       model=model_id,
                       sequence_length=512
                       , model_revision='master') # sequence_length 代表最大文本长度，默认值为128

# 当输入包含“soure_sentence”与“sentences_to_compare”时，会输出source_sentence中首个句子与sentences_to_compare中每个句子的向量表示，以及source_sentence中首个句子与sentences_to_compare中每个句子的相似度。
inputs = {
        "source_sentence": ["吃完海鲜可以喝牛奶吗?"],
        "sentences_to_compare": [
            "不可以，早晨喝牛奶不科学",
            "吃了海鲜后是不能再喝牛奶的，因为牛奶中含得有维生素C，如果海鲜喝牛奶一起服用会对人体造成一定的伤害",
            "吃海鲜是不能同时喝牛奶吃水果，这个至少间隔6小时以上才可以。",
            "吃海鲜是不可以吃柠檬的因为其中的维生素C会和海鲜中的矿物质形成砷"
        ]
    }

result = pipeline_se(input=inputs)
print (result)
'''
{'text_embedding': array([[ 1.6415151e-04,  2.2334497e-02, -2.4202393e-02, ...,
         2.7710509e-02,  2.5980933e-02, -3.1285528e-02],
       [-9.9107623e-03,  1.3627578e-03, -2.1072682e-02, ...,
         2.6786461e-02,  3.5029035e-03, -1.5877936e-02],
       [ 1.9877627e-03,  2.2191243e-02, -2.7656069e-02, ...,
         2.2540951e-02,  2.1780970e-02, -3.0861111e-02],
       [ 3.8688166e-05,  1.3409532e-02, -2.9691193e-02, ...,
         2.9900728e-02,  2.1570563e-02, -2.0719109e-02],
       [ 1.4484422e-03,  8.5943500e-03, -1.6661938e-02, ...,
         2.0832840e-02,  2.3828523e-02, -1.1581291e-02]], dtype=float32), 'scores': [0.8859604597091675, 0.9830712080001831, 0.966042160987854, 0.891857922077179]}
'''


# 当输入仅含有soure_sentence时，会输出source_sentence中每个句子的向量表示。
inputs2 = {
        "source_sentence": [
            "不可以，早晨喝牛奶不科学",
            "吃了海鲜后是不能再喝牛奶的，因为牛奶中含得有维生素C，如果海鲜喝牛奶一起服用会对人体造成一定的伤害",
            "吃海鲜是不能同时喝牛奶吃水果，这个至少间隔6小时以上才可以。",
            "吃海鲜是不可以吃柠檬的因为其中的维生素C会和海鲜中的矿物质形成砷"
        ]
}
result = pipeline_se(input=inputs2)
print (result)
'''
{'text_embedding': array([[-9.9107623e-03,  1.3627578e-03, -2.1072682e-02, ...,
         2.6786461e-02,  3.5029035e-03, -1.5877936e-02],
       [ 1.9877627e-03,  2.2191243e-02, -2.7656069e-02, ...,
         2.2540951e-02,  2.1780970e-02, -3.0861111e-02],
       [ 3.8688166e-05,  1.3409532e-02, -2.9691193e-02, ...,
         2.9900728e-02,  2.1570563e-02, -2.0719109e-02],
       [ 1.4484422e-03,  8.5943500e-03, -1.6661938e-02, ...,
         2.0832840e-02,  2.3828523e-02, -1.1581291e-02]], dtype=float32), 'scores': []}
'''
```

**默认向量维度768, scores中的score计算两个向量之间的内成积距离得到**

### 模型局限性以及可能的偏差

本模型基于Dureader Retrieval中文数据集(通用领域)上训练，在垂类领域英文文本上的文本效果会有降低，请用户自行评测后决定如何使用


### 训练示例代码

```python
# 需在GPU环境运行
# 加载数据集过程可能由于网络原因失败，请尝试重新运行代码
from modelscope.metainfo import Trainers                                                                                                                                                              
from modelscope.msdatasets import MsDataset
from modelscope.trainers import build_trainer
import tempfile
import os

tmp_dir = tempfile.TemporaryDirectory().name
if not os.path.exists(tmp_dir):
    os.makedirs(tmp_dir)

# load dataset
ds = MsDataset.load('dureader-retrieval-ranking', 'zyznull')
train_ds = ds['train'].to_hf_dataset()
dev_ds = ds['dev'].to_hf_dataset()
model_id = 'iic/nlp_gte_sentence-embedding_chinese-base'
def cfg_modify_fn(cfg):
    cfg.task = 'sentence-embedding'
    cfg['preprocessor'] = {'type': 'sentence-embedding','max_length': 256}
    cfg['dataset'] = {
        'train': {
            'type': 'bert',
            'query_sequence': 'query',
            'pos_sequence': 'positive_passages',
            'neg_sequence': 'negative_passages',
            'text_fileds': ['text'],
            'qid_field': 'query_id'
        },
        'val': {
            'type': 'bert',
            'query_sequence': 'query',
            'pos_sequence': 'positive_passages',
            'neg_sequence': 'negative_passages',
            'text_fileds': ['text'],
            'qid_field': 'query_id'
        },
    }
    cfg['train']['neg_samples'] = 4
    cfg['evaluation']['dataloader']['batch_size_per_gpu'] = 30
    cfg.train.max_epochs = 1
    cfg.train.train_batch_size = 4
    return cfg 
kwargs = dict(
    model=model_id,
    train_dataset=train_ds,
    work_dir=tmp_dir,
    eval_dataset=dev_ds,
    cfg_modify_fn=cfg_modify_fn)
trainer = build_trainer(name=Trainers.nlp_sentence_embedding_trainer, default_args=kwargs)
trainer.train()
```

### 模型效果评估

中文多任务向量评测榜单C-MTEB结果如下：

| Model               | Model Size (GB) | Embedding Dimensions | Sequence Length | Average (35 datasets) | Classification  (9 datasets)         | Clustering (4 datasets)        | Pair Classification        (2 datasets) | Reranking (4 datasets)         | Retrieval  (8 datasets)      | STS         (8 datasets) |
| ------------------- | -------------- | -------------------- | ---------------- | --------------------- | ------------------------------------ | ------------------------------ | --------------------------------------- | ------------------------------ | ---------------------------- | ------------------------ |
| gte-base-zh         | 0.21           | 768                  | 512              | 65.17                 | 69.62                                | 50.73                          | 80.12                                   | 66.57                          | 71.11                        | 56.99                    |
| stella-large-zh-v2  | 0.65           | 1024                 | 1024             | 65.13                 | 69.05                                | 49.16                          | 82.68                                   | 66.41                          | 70.14                        | 58.66                    |
| stella-large-zh     | 0.65           | 1024                 | 1024             | 64.54                 | 67.62                                | 48.65                          | 78.72                                   | 65.98                          | 71.02                        | 58.3                     |
| bge-large-zh-v1.5   | 1.3            | 1024                 | 512              | 64.53                 | 69.13                                | 48.99                          | 81.6                                    | 65.84                          | 70.46                        | 56.25                    |
| stella-base-zh-v2   | 0.21           | 768                  | 1024             | 64.36                 | 68.29                                | 49.4                           | 79.96                                   | 66.1                           | 70.08                        | 56.92                    |
| stella-base-zh      | 0.21           | 768                  | 1024             | 64.16                 | 67.77                                | 48.7                           | 76.09                                   | 66.95                          | 71.07                        | 56.54                    |
| piccolo-large-zh    | 0.65           | 1024                 | 512              | 64.11                 | 67.03                                | 47.04                          | 78.38                                   | 65.98                          | 70.93                        | 58.02                    |
| piccolo-base-zh     | 0.2            | 768                  | 512              | 63.66                 | 66.98                                | 47.12                          | 76.61                                   | 66.68                          | 71.2                         | 55.9                     |

## 引用

```BibTeX
@misc{li2023general,
      title={Towards General Text Embeddings with Multi-stage Contrastive Learning}, 
      author={Zehan Li and Xin Zhang and Yanzhao Zhang and Dingkun Long and Pengjun Xie and Meishan Zhang},
      year={2023},
      eprint={2308.03281},
      archivePrefix={arXiv},
      primaryClass={cs.CL}
}
```