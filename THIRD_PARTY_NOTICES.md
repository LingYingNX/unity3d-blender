# Third Party Notices

This project bundles or references third-party components. Their original licenses remain in effect.

本项目的 Unity AssetBundle 解析、FBX 导出和贴图导出能力基于 AssetStudio 的代码和库构建。发布本项目时必须保留 AssetStudio 的 upstream 链接、版权声明和 MIT License 文本。

## AssetStudio

The converter is based on AssetStudio code and libraries.

- Project: https://github.com/Perfare/AssetStudio
- License: MIT

AssetStudio MIT license notice:

```text
MIT License

Copyright (c) 2016 Radu
Copyright (c) 2016-2020 Perfare

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

## Bundled runtime dependencies

The Blender add-on zip includes the converter runtime and dependency DLLs, including AssetStudio, Mono.Cecil, K4os.Compression.LZ4, SixLabors.ImageSharp, SixLabors.Fonts, and native helper DLLs used by AssetStudio.

These dependencies are redistributed only to make the Blender add-on installable. Review each dependency's upstream license before redistributing modified builds.

## AssetRipper

AssetRipper is not bundled in this project and is not required by the current converter.
