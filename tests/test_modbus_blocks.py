from multiregistrator.common.models import RegisterConfig
from multiregistrator.server.modbus import build_read_blocks


def test_merges_contiguous_registers():
    registers = [
        RegisterConfig(name="a", address=1),
        RegisterConfig(name="b", address=2),
        RegisterConfig(name="c", address=3),
    ]
    blocks = build_read_blocks(registers)
    assert len(blocks) == 1
    assert blocks[0].start == 1
    assert blocks[0].count == 3
    assert [r.name for r in blocks[0].registers] == ["a", "b", "c"]


def test_merges_close_registers_within_gap():
    registers = [
        RegisterConfig(name="a", address=1),
        RegisterConfig(name="b", address=5),
    ]
    blocks = build_read_blocks(registers, max_gap=8)
    assert len(blocks) == 1
    assert blocks[0].count == 5


def test_splits_when_gap_too_large():
    registers = [
        RegisterConfig(name="a", address=1),
        RegisterConfig(name="b", address=50),
    ]
    blocks = build_read_blocks(registers, max_gap=8)
    assert len(blocks) == 2


def test_32bit_register_occupies_two_slots():
    registers = [
        RegisterConfig(name="f", address=1, data_type="float32"),
        RegisterConfig(name="a", address=3),
    ]
    blocks = build_read_blocks(registers)
    assert len(blocks) == 1
    assert blocks[0].count == 3


def test_splits_by_function_family():
    registers = [
        RegisterConfig(name="h", address=1, function="holding"),
        RegisterConfig(name="i", address=1, function="input"),
        RegisterConfig(name="c", address=1, function="coil"),
        RegisterConfig(name="d", address=1, function="discrete"),
    ]
    blocks = build_read_blocks(registers)
    assert len(blocks) == 4
    assert {b.function for b in blocks} == {"holding", "input", "coil", "discrete"}


def test_respects_max_register_limit():
    registers = [RegisterConfig(name=f"r{i}", address=i, data_type="uint16") for i in range(300)]
    blocks = build_read_blocks(registers, max_registers=125, max_gap=8)
    assert all(b.count <= 125 for b in blocks)
    assert sum(len(b.registers) for b in blocks) == 300
    assert len(blocks) >= 3


def test_empty_register_list():
    assert build_read_blocks([]) == []
