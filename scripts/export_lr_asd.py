"""Gera ``assets/models/lr_asd_ava.onnx`` a partir dos pesos publicados do LR-ASD.

Uso (fora do app, com PyTorch e onnx instalados):

    git clone --depth 1 https://github.com/Junhua-Liao/LR-ASD
    python scripts/export_lr_asd.py LR-ASD assets/models/lr_asd_ava.onnx

LR-ASD (Liao et al., IJCV 2025, licença MIT) detecta quem está falando: recebe 25 recortes
por segundo do rosto (112x112, cinza) e o MFCC do áudio no mesmo trecho e devolve, quadro a
quadro, uma nota (logit) de "falando". Os pesos são os ``pretrain_AVA.model`` dos autores.
O ONNX sai com uma entrada de áudio ``(1, 4T, 13)``, uma de vídeo ``(1, T, 112, 112)`` e a
saída ``(T,)`` = logit(falando) - logit(calado), com T livre.
"""
from __future__ import annotations

import sys
from pathlib import Path


def main(repo: str, output: str) -> None:
    import numpy as np
    import onnxruntime
    import torch
    from torch import nn

    sys.path.insert(0, repo)
    from loss import lossAV  # type: ignore[import-not-found]
    from model.Model import ASD_Model  # type: ignore[import-not-found]

    class Full(nn.Module):
        def __init__(self) -> None:
            super().__init__()
            self.model = ASD_Model()
            self.lossAV = lossAV()

        def forward(self, audio, video):
            a = self.model.forward_audio_frontend(audio)
            v = self.model.forward_visual_frontend(video)
            x = self.lossAV.FC(self.model.forward_audio_visual_backend(a, v))
            return x[:, 1] - x[:, 0]

    model = Full()
    state = torch.load(Path(repo) / "weight" / "pretrain_AVA.model", map_location="cpu")
    own = model.state_dict()
    for key, value in state.items():
        name = key.replace("module.", "")
        if name in own and own[name].shape == value.shape:
            own[name].copy_(value)
    model.eval()
    # O MaxPool3d do áudio recebe tensor 4D (sem lote) e não exporta para ONNX; o MaxPool2d
    # abaixo faz exatamente a mesma conta.
    encoder = model.model.audioEncoder
    probe = torch.randn(1, 1, 37, 13)
    for name in ("pool1", "pool2"):
        replacement = nn.MaxPool2d(kernel_size=(1, 3), stride=(1, 2), padding=(0, 1))
        assert torch.equal(getattr(encoder, name)(probe), replacement(probe))
        setattr(encoder, name, replacement)

    frames = 50
    audio = torch.randn(1, frames * 4, 13)
    video = torch.randint(0, 255, (1, frames, 112, 112)).float()
    torch.onnx.export(model, (audio, video), output, input_names=["audio", "video"],
                      output_names=["score"], opset_version=17, dynamo=False,
                      dynamic_axes={"audio": {1: "frames4"}, "video": {1: "frames"},
                                    "score": {0: "frames"}})
    session = onnxruntime.InferenceSession(output)
    for frames in (13, 50, 100):
        audio = torch.randn(1, frames * 4, 13)
        video = torch.randint(0, 255, (1, frames, 112, 112)).float()
        with torch.no_grad():
            expected = model(audio, video).numpy()
        got = session.run(None, {"audio": audio.numpy(), "video": video.numpy()})[0]
        assert float(np.abs(got - expected).max()) < 1e-3, "ONNX diverge do PyTorch"
    print(f"ok: {output}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
