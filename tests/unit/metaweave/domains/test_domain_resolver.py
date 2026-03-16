"""DomainResolver 单元测试"""

from pathlib import Path

import pytest
import yaml

from metaweave.core.domains.resolver import DomainResolver


def _write_yaml(tmp_path: Path, data: dict) -> Path:
    path = tmp_path / "db_domains.yaml"
    path.write_text(yaml.dump(data, allow_unicode=True), encoding="utf-8")
    return path


SAMPLE_CONFIG = {
    "database": {"name": "dvdrental", "description": "DVD租赁"},
    "domains": [
        {
            "name": "客户管理",
            "description": "客户相关",
            "tables": ["dvdrental.public.customer", "dvdrental.public.address"],
        },
        {
            "name": "影片资产",
            "description": "影片相关",
            "tables": [
                "dvdrental.public.film",
                "dvdrental.public.language",
                "dvdrental.public.customer",  # customer 跨域
            ],
        },
        {
            "name": "_未分类_",
            "description": "未分类",
            "tables": [],
        },
    ],
}


class TestInit:
    def test_load_normal(self, tmp_path):
        path = _write_yaml(tmp_path, SAMPLE_CONFIG)
        resolver = DomainResolver(path)
        assert len(resolver.get_all_domains()) == 3

    def test_file_not_exist(self, tmp_path):
        resolver = DomainResolver(tmp_path / "nonexistent.yaml")
        assert resolver.get_all_domains() == []
        assert resolver.get_domains_for_full_name("any.table") == []

    def test_empty_yaml(self, tmp_path):
        path = tmp_path / "db_domains.yaml"
        path.write_text("", encoding="utf-8")
        resolver = DomainResolver(path)
        assert resolver.get_all_domains() == []

    def test_invalid_yaml(self, tmp_path):
        path = tmp_path / "db_domains.yaml"
        path.write_text("{{invalid", encoding="utf-8")
        resolver = DomainResolver(path)
        assert resolver.get_all_domains() == []


class TestCoreLookup:
    @pytest.fixture()
    def resolver(self, tmp_path):
        path = _write_yaml(tmp_path, SAMPLE_CONFIG)
        return DomainResolver(path)

    def test_get_domains_for_full_name(self, resolver):
        domains = resolver.get_domains_for_full_name("dvdrental.public.customer")
        assert set(domains) == {"客户管理", "影片资产"}

    def test_case_insensitive(self, resolver):
        domains = resolver.get_domains_for_full_name("DVDRENTAL.PUBLIC.CUSTOMER")
        assert set(domains) == {"客户管理", "影片资产"}

    def test_not_found(self, resolver):
        assert resolver.get_domains_for_full_name("no.such.table") == []

    def test_get_tables_for_domain(self, resolver):
        tables = resolver.get_tables_for_domain("客户管理")
        assert "dvdrental.public.customer" in tables
        assert "dvdrental.public.address" in tables

    def test_get_tables_for_empty_domain(self, resolver):
        # _未分类_ 没有表，不在 _domain_to_tables 中
        assert resolver.get_tables_for_domain("_未分类_") == []

    def test_get_all_domains_includes_uncategorized(self, resolver):
        all_domains = resolver.get_all_domains()
        assert "_未分类_" in all_domains

    def test_build_domain_table_map(self, resolver):
        dtm = resolver.build_domain_table_map()
        assert "客户管理" in dtm
        assert "影片资产" in dtm
        # _未分类_ tables 为空，不出现在 map 中
        assert "_未分类_" not in dtm


class TestConvenience:
    @pytest.fixture()
    def resolver(self, tmp_path):
        path = _write_yaml(tmp_path, SAMPLE_CONFIG)
        return DomainResolver(path)

    def test_normalize_table_name_with_db(self):
        result = DomainResolver.normalize_table_name("public.customer", "dvdrental")
        assert result == "dvdrental.public.customer"

    def test_normalize_table_name_already_full(self):
        result = DomainResolver.normalize_table_name(
            "dvdrental.public.customer", "dvdrental"
        )
        assert result == "dvdrental.public.customer"

    def test_normalize_table_name_no_db(self):
        result = DomainResolver.normalize_table_name("public.customer")
        assert result == "public.customer"

    def test_get_domains_for_schema_table(self, resolver):
        domains = resolver.get_domains_for_schema_table("public.customer", "dvdrental")
        assert set(domains) == {"客户管理", "影片资产"}


class TestResolveTablePairs:
    @pytest.fixture()
    def resolver(self, tmp_path):
        path = _write_yaml(tmp_path, SAMPLE_CONFIG)
        return DomainResolver(path)

    def test_no_filter_no_cross(self, resolver):
        """无 domain filter 时返回全量组合"""
        tables = ["t1", "t2", "t3"]
        pairs = resolver.resolve_table_pairs(tables)
        assert len(pairs) == 3  # C(3,2)

    def test_intra_domain_filter(self, resolver):
        """指定 domain 只返回域内表对"""
        available = [
            "dvdrental.public.customer",
            "dvdrental.public.address",
            "dvdrental.public.film",
        ]
        pairs = resolver.resolve_table_pairs(
            available, domain_filter="客户管理", cross_domain=False
        )
        # 客户管理 域内有 customer 和 address
        assert len(pairs) == 1
        pair_set = {frozenset(p) for p in pairs}
        assert frozenset(
            ["dvdrental.public.customer", "dvdrental.public.address"]
        ) in pair_set

    def test_cross_domain(self, resolver):
        """跨域模式会产生域内+跨域表对"""
        available = [
            "dvdrental.public.customer",
            "dvdrental.public.address",
            "dvdrental.public.film",
            "dvdrental.public.language",
        ]
        pairs = resolver.resolve_table_pairs(
            available, domain_filter="all", cross_domain=True
        )
        # 域内: 客户管理 C(2,2)=1, 影片资产 C(3,2)=3 → intra=4
        # 跨域: address × {film, language} 减去已有的 → 额外 cross pairs
        assert len(pairs) > 4

    def test_available_tables_intersection(self, resolver):
        """只使用 available_tables 中存在的表"""
        available = ["dvdrental.public.customer"]
        pairs = resolver.resolve_table_pairs(
            available, domain_filter="客户管理", cross_domain=False
        )
        # 只有 1 个表，无法组合
        assert pairs == []

    def test_domain_filter_all(self, resolver):
        """domain_filter='all' 使用所有域"""
        available = [
            "dvdrental.public.customer",
            "dvdrental.public.address",
            "dvdrental.public.film",
        ]
        pairs = resolver.resolve_table_pairs(
            available, domain_filter="all", cross_domain=False
        )
        # 客户管理: (customer, address), 影片资产: (film, customer)
        assert len(pairs) == 2

    def test_case_insensitive_matching(self, resolver):
        """available_tables 大小写不同也能匹配"""
        available = [
            "DVDRENTAL.PUBLIC.CUSTOMER",
            "DVDRENTAL.PUBLIC.ADDRESS",
        ]
        pairs = resolver.resolve_table_pairs(
            available, domain_filter="客户管理", cross_domain=False
        )
        assert len(pairs) == 1
