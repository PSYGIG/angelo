#!/usr/bin/env bash
# 
# Script to compile angelo into a binary and upload as a release asset using the GitHub API v3.
#
# This script accepts the following parameters:
#
# * tag
# * github_user
# * github_api_token
#
# Script to upload a release asset using the GitHub API v3.
#
# Example:
#
# build-upload-github-asset.sh github_user=psygig-production github_api_token=TOKEN tag=2020.4.23
#
# Based on script from:
# 
# Author: Stefan Buck
# License: MIT
# https://gist.github.com/stefanbuck/ce788fee19ab6eb0b4447a85fc99f447
#
#

# Check dependencies.
set -e
xargs=$(which gxargs || which xargs)

# Validate settings.
[ "$TRACE" ] && set -x

CONFIG=$@

for line in $CONFIG; do
  eval "$line"
done

# Define variables.
owner=PSYGIG
repo=angelo
filename="dist/$repo-$(uname -s)-$(uname -m)"

GH_URL="https://$github_user:$github_api_token@github.com/PSYGIG/$repo.git"
GH_API="https://api.github.com"
GH_REPO="$GH_API/repos/$owner/$repo"
GH_TAGS="$GH_REPO/releases/tags/$tag"
AUTH="Authorization: token $github_api_token"
WGET_ARGS="--content-disposition --auth-no-challenge --no-cookie"
CURL_ARGS="-LJO#"

if [[ "$tag" == 'LATEST' ]]; then
  GH_TAGS="$GH_REPO/releases/latest"
fi

# Clone and checkout tag
repodir="$repo-$tag"
git clone --branch "$tag" --depth 1 "$GH_URL" "$repodir"

# Build binary
cd "$repodir"
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install https://github.com/pyinstaller/pyinstaller/tarball/develop 
pyinstaller --onefile --exclude-module PyInstaller "$repo.spec"
deactivate
mv "dist/$repo" "$filename"

# Validate token.
curl -o /dev/null -sH "$AUTH" $GH_REPO || { echo "Error: Invalid repo, token or network issue!";  exit 1; }

# Read asset tags.
response=$(curl -sH "$AUTH" $GH_TAGS)

# Get ID of the asset based on given filename.
eval $(echo "$response" | grep -m 1 "id.:" | grep -w id | tr : = | tr -cd '[[:alnum:]]=')
[ "$id" ] || { echo "Error: Failed to get release id for tag: $tag"; echo "$response" | awk 'length($0)<100' >&2; exit 1; }

# Upload asset
echo "Uploading asset... "

# Construct url
GH_ASSET="https://uploads.github.com/repos/$owner/$repo/releases/$id/assets?name=$(basename $filename)"

curl "$GITHUB_OAUTH_BASIC" --data-binary @"$filename" -H "Authorization: token $github_api_token" -H "Content-Type: application/octet-stream" $GH_ASSET