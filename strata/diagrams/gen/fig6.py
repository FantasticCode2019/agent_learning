# -*- coding: utf-8 -*-
from swim import render, export

CFG = {
    "slug": "fig6_decode",
    "title": "Strata decode 单层接力",
    "desc": "一层之内 GPU 与主线程的交接：GPU 跑图并在 router 之后敲 doorbell，主线程在 mapped pinned 内存上自旋醒来，"
            "把未命中专家交给 CPU 池，回填 parts 后启动 post 与下一层，48 层之后 head 出 logits，采样在图外。",
    "eyebrow": "Process · Strata Decode",
    "h1": "一层之内，谁在等谁",
    "lanes": [("主线程", "HOST"), ("GPU 流", "GPU"), ("CPU 池", "POOL")],
    "steps": ["写输入", "前向", "敲门", "唤醒", "算专家", "回填", "head", "采样"],
    "focal_step": 2,
    "focal_label": "焦点路径：doorbell 交接",
    "flow_label": "角色交接",
    "hint": "左 = 输入 · 右 = 输出",
    "data": [("DB", "张量：x/ids/w · parts"), ("WB", "控制字：h_seq")],
    "nodes": [
        dict(lane=0, step=0, title="写图输入", sub="stage_token(pos)", tool="指针 · 位置", cout="DB"),
        dict(lane=1, step=1, title="一层前向", sub="gr_read → mixer", tool="router 512 选 10"),
        dict(lane=1, step=2, title="敲门", sub="写 h_seq · ids · w", tool="图内 doorbell", cout="WB", focal=True),
        dict(lane=0, step=3, title="自旋唤醒", sub="每轮 cudaEventQuery", tool="0.05 ms 就醒", cin="WB"),
        dict(lane=2, step=4, title="算未命中", sub="只算 cache miss", tool="AVX-512 / AVX2", cout="DB"),
        dict(lane=0, step=5, title="回填 · 下一层", sub="H2D parts → post", tool="combine + gr_write", cin="DB"),
        dict(lane=1, step=6, title="head → logits", sub="48 层跑完之后", tool="图内 · T 行一次", cout="DB"),
        dict(lane=0, step=7, title="采样 · 接受", sub="argmax → commit", tool="在图外做"),
    ],
}

if __name__ == "__main__":
    w, h = render(CFG)
    export(CFG["slug"], w=w, h=h)
    print(CFG["slug"], w, h)
