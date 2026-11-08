#!/usr/bin/env bash
# Time the check on the server's own CPU, in a throwaway container of the acervo-server image.
#
#   NAS_ADMIN_PASSWORD=… experiments/take-verification/nas_timing.sh HOST BUNDLE > results/nas-timing.jsonl
#
# HOST is an ssh alias; BUNDLE a local directory holding `clips/`, `clips.jsonl`, `check.py` and
# `nas_timing.py`. Those few megabytes are copied into a scratch directory in the ssh user's home;
# the host then fetches the weights from Hugging Face and faster-whisper's wheels from PyPI itself,
# since gigabytes over the laptop's uplink took longer than the measurement. The scratch directory
# is mounted alone at /work; the container runs as that user, with no network and a low CPU share
# so the running services keep priority, and is removed when it exits. The scratch directory is
# deleted, and the container stopped, at the end whatever happened. The password is read from the environment and reaches only
# `sudo -S`.
set -euo pipefail
host=$1
bundle=$2
docker=${DOCKER:-/var/packages/ContainerManager/target/usr/bin/docker}
scratch=take-verification-timing

# Stopping the ssh client does not stop a `docker run` it started, so the container has a fixed name
# and the cleanup stops it by that name before deleting what it mounts.
cleanup() {
  ssh -T "$host" "sudo -S -p '' $docker stop -t 2 $scratch >/dev/null 2>&1; rm -rf ~/$scratch" \
    <<< "$NAS_ADMIN_PASSWORD" || true
}
trap cleanup EXIT

rsync -a --delete --exclude weights --exclude pylib "$bundle"/ "$host:$scratch/" >&2
ssh -T "$host" "cd ~/$scratch && bash -s" >&2 <<'FETCH'
set -euo pipefail
hf=https://huggingface.co
tf_files="config.json generation_config.json preprocessor_config.json tokenizer.json tokenizer_config.json
  vocab.json merges.txt normalizer.json added_tokens.json special_tokens_map.json model.safetensors"
fetch() {  # repo, directory, files…
  local repo=$1 dir=$2; shift 2
  mkdir -p "weights/$dir"
  for file in "$@"; do curl -sSfL -o "weights/$dir/$file" "$hf/$repo/resolve/main/$file"; done
}
fetch openai/whisper-base tf-base $tf_files
fetch openai/whisper-small tf-small $tf_files
fetch openai/whisper-large-v3-turbo tf-turbo $tf_files
fetch Systran/faster-whisper-base ct2-base config.json model.bin tokenizer.json vocabulary.txt
fetch Systran/faster-whisper-small ct2-small config.json model.bin tokenizer.json vocabulary.txt
fetch mobiuslabsgmbh/faster-whisper-large-v3-turbo ct2-turbo config.json model.bin tokenizer.json \
  vocabulary.json preprocessor_config.json
mkdir -p wheels pylib
for url in \
  https://files.pythonhosted.org/packages/05/99/49ee85903dee060d9f08297b4a342e5e0bcfca2f027a07b4ee0a38ab13f9/faster_whisper-1.2.1-py3-none-any.whl \
  https://files.pythonhosted.org/packages/bb/84/e1c6a2ecfb7cd53c5fd1343772cf49cd1aba62048af1d7ecb87a73b201f4/ctranslate2-4.8.5-cp312-cp312-manylinux_2_27_x86_64.manylinux_2_28_x86_64.whl \
  https://files.pythonhosted.org/packages/e1/7f/9f1237feb894afa472ef834aa1fbfe4d6398f28dc7e86a1b418650204c36/av-19.0.2-cp312-abi3-manylinux_2_28_x86_64.whl
do
  curl -sSfL -o "wheels/${url##*/}" "$url"
  python3 -m zipfile -e "wheels/${url##*/}" pylib/
done
du -sh weights pylib
FETCH

run() {
  ssh -T "$host" "cd ~/$scratch && sudo -S -p '' $docker run --rm --name $scratch --network none --cpu-shares 256 \
    --user \$(id -u):\$(id -g) -e HF_HUB_OFFLINE=1 -e HOME=/work -v \$PWD:/work -w /work \
    --entrypoint python acervo-server:latest /work/nas_timing.py $*" <<< "$NAS_ADMIN_PASSWORD"
}
for model in base small turbo; do
  run --engine ctranslate2 --model "$model" --threads 4
  run --engine transformers --model "$model" --threads 4
done
run --engine ctranslate2 --model small --threads 2
run --engine transformers --model small --threads 2
