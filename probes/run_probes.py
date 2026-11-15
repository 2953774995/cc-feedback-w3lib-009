#!/usr/bin/env python3
"""URL 批量规范化去重验收探针。

契约：
  from w3lib.url_batch import normalize_many
  res = normalize_many(urls, drop_tracking=True)
  res.unique      规范化后去重的 URL 列表，保持首次出现顺序
  res.duplicates  {规范化 URL: [被合并掉的原始 URL, ...]}
  res.invalid     无法解析的原始输入列表，不抛异常
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

FAILED = 0
PASSED = 0


def check(code, desc, fn):
    global FAILED, PASSED
    try:
        fn()
        print(f"[PASS] {code} {desc}")
        PASSED += 1
    except Exception as exc:  # noqa: BLE001
        print(f"[FAIL] {code} {desc}")
        print(f"        {type(exc).__name__}: {exc}")
        FAILED += 1


def main():
    try:
        from w3lib.url_batch import normalize_many  # noqa: F401
    except Exception as exc:  # noqa: BLE001
        print(f"[FAIL] P0 导入 w3lib.url_batch 失败：{type(exc).__name__}: {exc}")
        print("-" * 60)
        print("探针汇总：0/7 通过")
        return 1

    def p1():
        r = normalize_many(["http://Example.COM/a"])
        assert r.unique == ["http://example.com/a"], r.unique

    def p2():
        r = normalize_many(["http://example.com:80/a", "http://example.com/a"])
        assert len(r.unique) == 1, r.unique
        assert len(r.duplicates[r.unique[0]]) == 1

    def p3():
        r = normalize_many(["https://x.com/p?utm_source=a&id=7&utm_medium=b"])
        assert "utm_" not in r.unique[0], r.unique[0]
        assert "id=7" in r.unique[0], r.unique[0]

    def p4():
        r = normalize_many(["https://x.com/p?utm_source=a"], drop_tracking=False)
        assert "utm_source" in r.unique[0], r.unique[0]

    def p5():
        r = normalize_many(["https://x.com/a#frag", "https://x.com/a"])
        assert len(r.unique) == 1, r.unique

    def p6():
        r = normalize_many(["https://x.com/1", "not a url:::", "https://x.com/2"])
        assert len(r.unique) == 2, r.unique
        assert len(r.invalid) == 1, r.invalid

    def p7():
        r = normalize_many(["https://x.com/b", "https://x.com/a", "https://x.com/b"])
        assert r.unique == ["https://x.com/b", "https://x.com/a"], r.unique

    check("P1", "主机小写规范化", p1)
    check("P2", "默认端口与重复项合并", p2)
    check("P3", "跟踪参数被剥掉", p3)
    check("P4", "关闭开关时保留跟踪参数", p4)
    check("P5", "片段参与去重", p5)
    check("P6", "非法输入进 invalid 不中断", p6)
    check("P7", "去重保持首次出现顺序", p7)

    print("-" * 60)
    print(f"探针汇总：{PASSED}/{PASSED + FAILED} 通过")
    return 0 if FAILED == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
