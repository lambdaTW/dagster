import pytest
from dagster import (
    AssetMaterialization,
    IOManager,
    IOManagerDefinition,
    PartitionsDefinition,
    StaticPartitionsDefinition,
)
from dagster.core.asset_defs import asset, build_assets_job
from dagster.core.asset_defs.asset_partitions import (
    get_downstream_partitions_for_partition_range,
    get_upstream_partitions_for_partition_range,
)
from dagster.core.asset_defs.partition_mapping import PartitionMapping
from dagster.core.definitions.events import AssetKey
from dagster.core.definitions.partition_key_range import PartitionKeyRange


def test_assets_with_same_partitioning():
    partitions_def = StaticPartitionsDefinition(["a", "b", "c", "d"])

    @asset(partitions_def=partitions_def)
    def upstream_asset():
        pass

    @asset(partitions_def=partitions_def)
    def downstream_asset(upstream_asset):
        assert upstream_asset

    assert (
        get_upstream_partitions_for_partition_range(
            downstream_asset,
            upstream_asset,
            AssetKey("upstream_asset"),
            PartitionKeyRange("a", "c"),
        )
        == PartitionKeyRange("a", "c")
    )

    assert (
        get_downstream_partitions_for_partition_range(
            downstream_asset,
            upstream_asset,
            AssetKey("upstream_asset"),
            PartitionKeyRange("a", "c"),
        )
        == PartitionKeyRange("a", "c")
    )


def test_filter_mapping_partitions_dep():
    downstream_partitions = ["john", "ringo", "paul", "george"]
    upstream_partitions = [
        f"{hemisphere}|{beatle}"
        for beatle in downstream_partitions
        for hemisphere in ["southern", "northern"]
    ]
    downstream_partitions_def = StaticPartitionsDefinition(downstream_partitions)
    upstream_partitions_def = StaticPartitionsDefinition(upstream_partitions)

    class HemisphereFilteringPartitionMapping(PartitionMapping):
        def __init__(self, hemisphere: str):
            self.hemisphere = hemisphere

        def get_upstream_partitions_for_partition_range(
            self,
            downstream_partition_key_range: PartitionKeyRange,
            downstream_partitions_def: PartitionsDefinition,  # pylint: disable=unused-argument
            upstream_partitions_def: PartitionsDefinition,  # pylint: disable=unused-argument
        ) -> PartitionKeyRange:
            return PartitionKeyRange(
                f"{self.hemisphere}|{downstream_partition_key_range.start}",
                f"{self.hemisphere}|{downstream_partition_key_range.end}",
            )

        def get_downstream_partitions_for_partition_range(
            self,
            upstream_partition_key_range: PartitionKeyRange,
            downstream_partitions_def: PartitionsDefinition,  # pylint: disable=unused-argument
            upstream_partitions_def: PartitionsDefinition,  # pylint: disable=unused-argument
        ) -> PartitionKeyRange:
            return PartitionKeyRange(
                upstream_partition_key_range.start.split("|")[-1],
                upstream_partition_key_range.end.split("|")[-1],
            )

    @asset(partitions_def=upstream_partitions_def)
    def upstream_asset():
        pass

    @asset(
        partitions_def=downstream_partitions_def,
        partition_mappings={"upstream_asset": HemisphereFilteringPartitionMapping("southern")},
    )
    def downstream_asset(upstream_asset):
        assert upstream_asset

    assert (
        get_upstream_partitions_for_partition_range(
            downstream_asset,
            upstream_asset,
            AssetKey("upstream_asset"),
            PartitionKeyRange("ringo", "paul"),
        )
        == PartitionKeyRange("southern|ringo", "southern|paul")
    )

    assert (
        get_downstream_partitions_for_partition_range(
            downstream_asset,
            upstream_asset,
            AssetKey("upstream_asset"),
            PartitionKeyRange("southern|ringo", "southern|paul"),
        )
        == PartitionKeyRange("ringo", "paul")
    )


def test_access_partition_keys_from_context():
    partitions_def = StaticPartitionsDefinition(["a", "b", "c", "d"])

    class MyIOManager(IOManager):
        def handle_output(self, context, obj):
            assert context.asset_partition_key == "b"

        def load_input(self, context):
            pass

    @asset(partitions_def=partitions_def)
    def my_asset():
        pass

    my_job = build_assets_job(
        "my_job",
        assets=[my_asset],
        resource_defs={"io_manager": IOManagerDefinition.hardcoded_io_manager(MyIOManager())},
    )
    result = my_job.execute_in_process(partition_key="b")
    assert result.asset_materializations_for_node("my_asset") == [
        AssetMaterialization(asset_key=AssetKey(["my_asset"]), partition="b")
    ]


def test_access_partition_keys_from_context_non_identity_partition_mapping():
    upstream_partitions_def = StaticPartitionsDefinition(["1", "2", "3"])
    downstream_partitions_def = StaticPartitionsDefinition(["2", "3"])

    class TrailingWindowPartitionMapping(PartitionMapping):
        """
        Maps each downstream partition to two partitions in the upstream asset: itself and the
        preceding partition.
        """

        def get_upstream_partitions_for_partition_range(
            self,
            downstream_partition_key_range: PartitionKeyRange,
            downstream_partitions_def: PartitionsDefinition,
            upstream_partitions_def: PartitionsDefinition,
        ) -> PartitionKeyRange:
            del downstream_partitions_def, upstream_partitions_def

            start, end = downstream_partition_key_range
            return PartitionKeyRange(str(int(start) - 1), end)

        def get_downstream_partitions_for_partition_range(
            self,
            upstream_partition_key_range: PartitionKeyRange,
            downstream_partitions_def: PartitionsDefinition,
            upstream_partitions_def: PartitionsDefinition,
        ) -> PartitionKeyRange:
            raise NotImplementedError()

    class MyIOManager(IOManager):
        def handle_output(self, context, obj):
            assert context.asset_partition_key == "2"

        def load_input(self, context):
            start, end = context.asset_partition_key_range
            assert start, end == ("1", "2")

    @asset(partitions_def=upstream_partitions_def)
    def upstream_asset(context):
        assert context.output_asset_partition_key() == "2"

    @asset(
        partitions_def=downstream_partitions_def,
        partition_mappings={"upstream_asset": TrailingWindowPartitionMapping()},
    )
    def downstream_asset(context, upstream_asset):
        assert context.output_asset_partition_key() == "2"
        assert upstream_asset is None

    my_job = build_assets_job(
        "my_job",
        assets=[upstream_asset, downstream_asset],
        resource_defs={"io_manager": IOManagerDefinition.hardcoded_io_manager(MyIOManager())},
    )
    result = my_job.execute_in_process(partition_key="2")
    assert result.asset_materializations_for_node("upstream_asset") == [
        AssetMaterialization(AssetKey(["upstream_asset"]), partition="2")
    ]
    assert result.asset_materializations_for_node("downstream_asset") == [
        AssetMaterialization(AssetKey(["downstream_asset"]), partition="2")
    ]


def test_access_partition_keys_from_context_only_one_asset_partitioned():
    upstream_partitions_def = StaticPartitionsDefinition(["a", "b", "c"])

    class MyIOManager(IOManager):
        def handle_output(self, context, obj):
            if context.op_def.name == "upstream_asset":
                assert context.asset_partition_key == "b"
            elif context.op_def.name == "downstream_asset":
                assert not context.has_asset_partitions
                with pytest.raises(Exception):  # TODO: better error message
                    assert context.asset_partition_key_range
            else:
                assert False

        def load_input(self, context):
            assert not context.has_asset_partitions

    @asset(partitions_def=upstream_partitions_def)
    def upstream_asset(context):
        assert context.output_asset_partition_key() == "b"

    @asset
    def downstream_asset(upstream_asset):
        assert upstream_asset is None

    my_job = build_assets_job(
        "my_job",
        assets=[upstream_asset, downstream_asset],
        resource_defs={"io_manager": IOManagerDefinition.hardcoded_io_manager(MyIOManager())},
    )
    result = my_job.execute_in_process(partition_key="b")
    assert result.asset_materializations_for_node("upstream_asset") == [
        AssetMaterialization(asset_key=AssetKey(["upstream_asset"]), partition="b")
    ]
