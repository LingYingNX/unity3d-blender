using System.Globalization;
using System.Text;
using System.Windows.Forms;
using AssetStudio;

Thread.CurrentThread.CurrentCulture = CultureInfo.InvariantCulture;
Thread.CurrentThread.CurrentUICulture = CultureInfo.InvariantCulture;

var job = ResolveExportJob(args);
if (job == null)
{
    return 2;
}

var input = job.InputPath;
var outputDir = job.OutputDirectory;
var fbxDir = Path.Combine(outputDir, "fbx");
var objDir = Path.Combine(outputDir, "obj");
var textureDir = Path.Combine(outputDir, "textures");

Directory.CreateDirectory(fbxDir);
Directory.CreateDirectory(objDir);
Directory.CreateDirectory(textureDir);

Console.WriteLine($"Loading: {input}");
var manager = new AssetsManager();
manager.LoadFiles(input);

var objects = manager.assetsFileList.SelectMany(file => file.Objects).ToList();
var gameObjects = objects.OfType<GameObject>().Where(go => go.m_Transform != null).ToList();
var meshes = objects.OfType<Mesh>().Where(mesh => mesh.m_VertexCount > 0).ToList();
var textures = objects.OfType<Texture2D>().ToList();

Console.WriteLine($"Assets files: {manager.assetsFileList.Count}");
Console.WriteLine($"GameObjects: {gameObjects.Count}");
Console.WriteLine($"Meshes: {meshes.Count}");
Console.WriteLine($"Textures: {textures.Count}");

var roots = gameObjects
    .Where(go => IsRoot(go) && HasMeshInSubtree(go))
    .OrderBy(go => go.m_Name, StringComparer.OrdinalIgnoreCase)
    .ToList();

if (roots.Count == 0)
{
    roots = gameObjects
        .Where(HasMeshInSubtree)
        .OrderBy(go => go.m_Name, StringComparer.OrdinalIgnoreCase)
        .ToList();
}

var fbxCount = 0;
foreach (var root in roots)
{
    var name = SafeName(string.IsNullOrWhiteSpace(root.m_Name) ? "model" : root.m_Name);
    var path = UniquePath(Path.Combine(fbxDir, name + ".fbx"));
    try
    {
        var converted = new ModelConverter(root, ImageFormat.Png);
        ModelExporter.ExportFbx(
            path,
            converted,
            eulerFilter: true,
            filterPrecision: 0.25f,
            allNodes: true,
            skins: true,
            animation: true,
            blendShape: true,
            castToBone: false,
            boneSize: 10f,
            exportAllUvsAsDiffuseMaps: false,
            scaleFactor: 1f,
            versionIndex: 3,
            isAscii: false);
        fbxCount++;
        Console.WriteLine($"FBX: {path}");
    }
    catch (Exception ex)
    {
        Console.Error.WriteLine($"FBX export failed for {root.m_Name}: {ex}");
    }
}

var objCount = 0;
foreach (var mesh in meshes.OrderBy(mesh => mesh.m_Name, StringComparer.OrdinalIgnoreCase))
{
    var name = SafeName(string.IsNullOrWhiteSpace(mesh.m_Name) ? "mesh" : mesh.m_Name);
    var path = UniquePath(Path.Combine(objDir, name + ".obj"));
    if (ExportObj(mesh, path))
    {
        objCount++;
    }
}

var textureCount = 0;
foreach (var texture in textures.OrderBy(texture => texture.m_Name, StringComparer.OrdinalIgnoreCase))
{
    var name = SafeName(string.IsNullOrWhiteSpace(texture.m_Name) ? "texture" : texture.m_Name);
    var path = UniquePath(Path.Combine(textureDir, name + ".png"));
    try
    {
        using var image = texture.ConvertToImage(flip: true);
        if (image == null)
        {
            continue;
        }

        using var stream = File.OpenWrite(path);
        image.WriteToStream(stream, ImageFormat.Png);
        textureCount++;
    }
    catch (Exception ex)
    {
        Console.Error.WriteLine($"Texture export failed for {texture.m_Name}: {ex}");
    }
}

Console.WriteLine($"Exported FBX: {fbxCount}");
Console.WriteLine($"Exported OBJ: {objCount}");
Console.WriteLine($"Exported PNG textures: {textureCount}");
Console.WriteLine($"Output: {outputDir}");

if (args.Length == 0)
{
    MessageBox.Show(
        $"导出完成。\n\nFBX: {fbxCount}\nOBJ: {objCount}\nPNG贴图: {textureCount}\n\n输出目录:\n{outputDir}",
        "AssetBundleToBlender",
        MessageBoxButtons.OK,
        MessageBoxIcon.Information);
}

return fbxCount > 0 || objCount > 0 ? 0 : 1;

static ExportJob? ResolveExportJob(string[] args)
{
    if (args.Length >= 2)
    {
        return new ExportJob(Path.GetFullPath(args[0]), Path.GetFullPath(args[1]));
    }

    if (args.Length == 1)
    {
        var input = Path.GetFullPath(args[0]);
        return new ExportJob(input, DefaultOutputDirectory(input));
    }

    using var dialog = new OpenFileDialog
    {
        Title = "选择 Unity3D / AssetBundle 文件",
        Filter = "Unity AssetBundle (*.unity3d;*.ab;*.bundle)|*.unity3d;*.ab;*.bundle|All files (*.*)|*.*",
        Multiselect = false,
        CheckFileExists = true
    };

    if (dialog.ShowDialog() != DialogResult.OK)
    {
        Console.Error.WriteLine("No file selected.");
        return null;
    }

    var selectedInput = Path.GetFullPath(dialog.FileName);
    return new ExportJob(selectedInput, DefaultOutputDirectory(selectedInput));
}

static string DefaultOutputDirectory(string input)
{
    return Path.Combine(Path.GetDirectoryName(input) ?? Directory.GetCurrentDirectory(), Path.GetFileNameWithoutExtension(input) + "_fbx_export");
}

static bool IsRoot(GameObject go)
{
    var transform = go.m_Transform;
    if (transform == null || transform.m_Father == null || transform.m_Father.IsNull)
    {
        return true;
    }

    return !transform.m_Father.TryGet(out _);
}

static bool HasMeshInSubtree(GameObject go)
{
    if (go.m_SkinnedMeshRenderer != null || go.m_MeshFilter != null)
    {
        return true;
    }

    var transform = go.m_Transform;
    if (transform?.m_Children == null)
    {
        return false;
    }

    foreach (var childPtr in transform.m_Children)
    {
        if (childPtr.TryGet(out var child) && child.m_GameObject.TryGet(out var childGo) && HasMeshInSubtree(childGo))
        {
            return true;
        }
    }

    return false;
}

static bool ExportObj(Mesh mesh, string path)
{
    if (mesh.m_VertexCount <= 0 || mesh.m_Vertices == null || mesh.m_Vertices.Length == 0)
    {
        return false;
    }

    var sb = new StringBuilder();
    sb.AppendLine("g " + SafeName(mesh.m_Name));

    var vertexStride = mesh.m_Vertices.Length == mesh.m_VertexCount * 4 ? 4 : 3;
    for (var v = 0; v < mesh.m_VertexCount; v++)
    {
        sb.Append(CultureInfo.InvariantCulture, $"v {-mesh.m_Vertices[v * vertexStride]} {mesh.m_Vertices[v * vertexStride + 1]} {mesh.m_Vertices[v * vertexStride + 2]}\n");
    }

    var uv0 = mesh.m_UV0;
    var hasUv = uv0?.Length > 0;
    var uvStride = 4;
    if (hasUv && uv0 != null)
    {
        if (uv0.Length == mesh.m_VertexCount * 2) uvStride = 2;
        else if (uv0.Length == mesh.m_VertexCount * 3) uvStride = 3;
        for (var v = 0; v < mesh.m_VertexCount; v++)
        {
            sb.Append(CultureInfo.InvariantCulture, $"vt {uv0[v * uvStride]} {uv0[v * uvStride + 1]}\n");
        }
    }

    var normals = mesh.m_Normals;
    var hasNormals = normals?.Length > 0;
    var normalStride = 3;
    if (hasNormals && normals != null)
    {
        normalStride = normals.Length == mesh.m_VertexCount * 4 ? 4 : 3;
        for (var v = 0; v < mesh.m_VertexCount; v++)
        {
            sb.Append(CultureInfo.InvariantCulture, $"vn {-normals[v * normalStride]} {normals[v * normalStride + 1]} {normals[v * normalStride + 2]}\n");
        }
    }

    var triangleOffset = 0;
    for (var i = 0; i < mesh.m_SubMeshes.Length; i++)
    {
        sb.AppendLine($"g {SafeName(mesh.m_Name)}_{i}");
        var indexCount = (int)mesh.m_SubMeshes[i].indexCount;
        var triangleEnd = triangleOffset + indexCount / 3;
        for (var f = triangleOffset; f < triangleEnd; f++)
        {
            var a = mesh.m_Indices[f * 3 + 2] + 1;
            var b = mesh.m_Indices[f * 3 + 1] + 1;
            var c = mesh.m_Indices[f * 3] + 1;
            if (hasUv && hasNormals)
            {
                sb.AppendLine($"f {a}/{a}/{a} {b}/{b}/{b} {c}/{c}/{c}");
            }
            else if (hasUv)
            {
                sb.AppendLine($"f {a}/{a} {b}/{b} {c}/{c}");
            }
            else if (hasNormals)
            {
                sb.AppendLine($"f {a}//{a} {b}//{b} {c}//{c}");
            }
            else
            {
                sb.AppendLine($"f {a} {b} {c}");
            }
        }
        triangleOffset = triangleEnd;
    }

    File.WriteAllText(path, sb.Replace("NaN", "0").ToString());
    return true;
}

static string SafeName(string value)
{
    var invalid = Path.GetInvalidFileNameChars();
    var cleaned = new string(value.Select(ch => invalid.Contains(ch) ? '_' : ch).ToArray()).Trim();
    return string.IsNullOrWhiteSpace(cleaned) ? "unnamed" : cleaned;
}

static string UniquePath(string path)
{
    if (!File.Exists(path))
    {
        return path;
    }

    var dir = Path.GetDirectoryName(path)!;
    var name = Path.GetFileNameWithoutExtension(path);
    var ext = Path.GetExtension(path);
    for (var i = 1; ; i++)
    {
        var candidate = Path.Combine(dir, $"{name}_{i}{ext}");
        if (!File.Exists(candidate))
        {
            return candidate;
        }
    }
}

internal sealed record ExportJob(string InputPath, string OutputDirectory);
