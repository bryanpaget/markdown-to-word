-- ascii-to-image.lua
-- Converts ```ascii blocks to PNG via ditaa and embeds using pandoc.mediabag.

local function run_ditaa(content)
  local tmp = os.tmpname() .. ".txt"
  local f = io.open(tmp, "w")
  if not f then
    io.stderr:write("Failed to create temp text file\n")
    return nil
  end
  f:write(content)
  f:close()

  local outfile = os.tmpname() .. ".png"
  local cmd = string.format("ditaa --scale 2.0 --no-antialias --round-corners --no-shadows %s %s", tmp, outfile)
  local ret = os.execute(cmd)
  os.remove(tmp)

  if not ret then
    io.stderr:write("ditaa failed\n")
    return nil
  end

  local img = io.open(outfile, "rb")
  if not img then
    io.stderr:write("Could not open generated PNG\n")
    return nil
  end
  local data = img:read("*all")
  img:close()
  os.remove(outfile)

  return data
end

function CodeBlock(el)
  if el.classes:includes("ascii") then
    local data = run_ditaa(el.text)
    if data then
      -- Use a media path (Pandoc will look inside the media bag)
      local name = "media/ascii-" .. os.time() .. ".png"
      pandoc.mediabag.insert(name, "image/png", data)
      local img = pandoc.Image({}, name)
      return pandoc.Para({img})
    else
      io.stderr:write("Fallback: keeping original code block\n")
      return el
    end
  end
end
