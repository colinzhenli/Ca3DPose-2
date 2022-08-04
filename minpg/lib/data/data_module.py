import pytorch_lightning as pl
from torch.utils.data import DataLoader
from minpg.lib.common_ops.functions import common_ops
from importlib import import_module
import numpy as np
import torch


class DataModule(pl.LightningDataModule):
    def __init__(self, data_cfg):
        super().__init__()
        self.data_cfg = data_cfg
        self.dataset = getattr(import_module('minpg.lib.data.dataset'), data_cfg.data.dataset)

    def setup(self, stage=None):
        if stage == "fit" or stage is None:
            self.train_set = self.dataset(self.data_cfg, "train")
            self.val_set = self.dataset(self.data_cfg, "val")
        if stage == "test" or stage is None:
            self.val_set = self.dataset(self.data_cfg, self.data_cfg.model.inference.split)
        if stage == "predict" or stage is None:
            self.test_set = self.dataset(self.data_cfg, "test")

    def train_dataloader(self):
        return DataLoader(self.train_set, batch_size=self.data_cfg.data.batch_size, shuffle=True, pin_memory=True,
                          collate_fn=sparse_collate_fn, num_workers=self.data_cfg.data.num_workers)

    def val_dataloader(self):
        return DataLoader(self.val_set, batch_size=1, pin_memory=True, collate_fn=sparse_collate_fn,
                          num_workers=self.data_cfg.data.num_workers)

    def test_dataloader(self):
        return DataLoader(self.val_set, batch_size=1, pin_memory=True, collate_fn=sparse_collate_fn,
                          num_workers=self.data_cfg.data.num_workers)

    def predict_dataloader(self):
        return DataLoader(self.test_set, batch_size=1, pin_memory=True, collate_fn=sparse_collate_fn,
                          num_workers=self.data_cfg.data.num_workers)


def sparse_collate_fn(batch):
    data = {}
    locs = []
    locs_scaled = []
    vert_batch_ids = []
    feats = []
    sem_labels = []
    instance_ids = []
    instance_info = []  # (N, 3)
    instance_num_point = []  # (total_nInst), int
    instance_offsets = [0]
    total_num_inst = 0
    instance_cls = []  # (total_nInst), long
    instance_bboxes = []

    scan_ids = []
    # total_num_points = 0
    # for b in batch:
    #     scan_ids.append(b["scan_id"])
    #     total_num_points += b["locs"].shape[0]
    #
    # locs = torch.empty((total_num_points, batch[0]["locs"].shape[1]), dtype=torch.float32)
    # locs_scaled = torch.empty((total_num_points, 3), dtype=torch.int32)
    # vert_batch_ids = torch.empty(total_num_points, dtype=torch.int32)
    # feats = torch.empty((total_num_points, batch[0]["feats"].shape[1]), dtype=torch.float32)
    # instance_ids = torch.empty(total_num_points, dtype=torch.int32)
    # sem_labels = torch.empty(total_num_points, dtype=torch.int32)


    for i, b in enumerate(batch):
        scan_ids.append(b["scan_id"])
        locs.append(torch.from_numpy(b["locs"]))

        locs_scaled.append(torch.from_numpy(b["locs_scaled"]).int())
        vert_batch_ids.append(torch.full((b["locs_scaled"].shape[0],), fill_value=i, dtype=torch.int16))
        feats.append(torch.from_numpy(b["feats"]))

        instance_ids_i = b["instance_ids"]
        instance_ids_i[instance_ids_i != -1] += total_num_inst
        total_num_inst += b["num_instance"].item()
        instance_ids.append(torch.from_numpy(instance_ids_i))

        sem_labels.append(torch.from_numpy(b["sem_labels"]))

        instance_info.append(torch.from_numpy(b["instance_info"]))
        instance_num_point.append(torch.from_numpy(b["instance_num_point"]))
        instance_offsets.append(instance_offsets[-1] + b["num_instance"].item())

        instance_cls.extend(b["instance_semantic_cls"])
        instance_bboxes.extend(b["instance_bboxes"])

    tmp_locs_scaled = torch.cat(locs_scaled, dim=0)  # long (N, 1 + 3), the batch item idx is put in locs[:, 0]
    data['scan_ids'] = scan_ids
    data["locs"] = torch.cat(locs, dim=0)  # float (N, 3)
    data["vert_batch_ids"] = torch.cat(vert_batch_ids, dim=0)
    data["feats"] = torch.cat(feats, dim=0)

    data["sem_labels"] = torch.cat(sem_labels, dim=0)  # int (N,)
    data["instance_ids"] = torch.cat(instance_ids, dim=0)  # int, (N,)
    data["instance_info"] = torch.cat(instance_info, dim=0)  # float (total_nInst, 3)
    data["instance_num_point"] = torch.cat(instance_num_point, dim=0)  # (total_nInst)
    data["instance_offsets"] = torch.tensor(instance_offsets, dtype=torch.int32)  # int (B+1)
    data["instance_semantic_cls"] = torch.tensor(instance_cls, dtype=torch.int32)  # long (total_nInst)
    data["instance_bboxes"] = torch.tensor(instance_bboxes, dtype=torch.float32)

    # voxelize
    data["voxel_locs"], data["v2p_map"], data["p2v_map"] = common_ops.voxelization_idx(tmp_locs_scaled,
                                                                                       data["vert_batch_ids"],
                                                                                       len(batch),
                                                                                       4)
    return data