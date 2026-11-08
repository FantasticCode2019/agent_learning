# -*- coding: utf-8 -*-
from swim import render, export

CFG = {
    "slug": "fig7_spec",
    "title": "Strata 投机窗口",
    "desc": "一个验证窗的六步：choose_window 选 T，草稿器出 T 条，主模型一次前向验证 T 行，主线程逐位比对接受 a 个，"
            "commit 回放 GDN 与 indexer，最后发 T 行并推进 p。",
    "eyebrow": "Process · Strata Speculation",
    "h1": "一个窗口，一次前向",
    "lanes": [("主线程", "HOST"), ("草稿器", "DRAFT"), ("主模型", "MODEL")],
    "steps": ["选窗", "出草稿", "验证", "比对", "commit", "发 token"],
    "focal_step": 2,
    "focal_label": "焦点路径：一次验证",
    "flow_label": "角色交接",
    "hint": "左 = 输入 · 右 = 输出",
    "data": [("DB", "token id：草稿 / logits"), ("WB", "写回：状态 / T 行")],
    "nodes": [
        dict(lane=0, step=0, title="选窗口", sub="choose_window", tool=">5% 才取 k>0"),
        dict(lane=1, step=1, title="出草稿", sub="MTP / DFlash2", tool="接受率 0.89 / 0.86", cout="DB"),
        dict(lane=2, step=2, title="验证 T 行", sub="48 层 + head 一次", tool="逐行 argmax", cout="DB", focal=True),
        dict(lane=0, step=3, title="逐位比对", sub="第一处不等就停", tool="a 个 + 1 bonus"),
        dict(lane=2, step=4, title="commit", sub="GDN 回放 · indexer", tool="commit(a+1)", cout="WB"),
        dict(lane=0, step=5, title="发 a+1 · 前进", sub="p += a+1", tool="未结束下一窗", cout="WB"),
    ],
}

if __name__ == "__main__":
    w, h = render(CFG)
    export(CFG["slug"], w=w, h=h)
    print(CFG["slug"], w, h)
