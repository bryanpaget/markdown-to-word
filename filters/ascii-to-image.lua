-- ascii-to-image.lua
-- Converts ```ascii blocks to PNG via ditaa, then outputs HTML for DOCX.
-- Falls back to the original code block if ditaa fails or is missing.

local function run_ditaa(content)
  local tmp = os.tmpname() .. ".txt"
  local f = io.open(tmp, "w")
  if not f then
    io.stderr:write("Failed to create temp file\n")
    return nil
  end
  f:write(content)
  f:close()

  local outfile = "ascii-diagram-" .. os.time() .. ".png"
  local cmd = string.format("ditaa --scale 2.0 --no-antialias --round-corners --no-shadows %s %s", tmp, outfile)
  local ret = os.execute(cmd)
  os.remove(tmp)

  if ret then
    local img = io.open(outfile, "r")
    if img then
      img:close()
      return outfile
    end
  end
  io.stderr:write("ditaa failed to create PNG, falling back to code block\n")
  return nil
end

function CodeBlock(el)
  if el.classes:includes("ascii") then
    local img_path = run_ditaa(el.text)
    if img_path then
      local html = string.format('<div style="text-align:center;border:1px solid black;padding:5px;"><img src="%s" style="max-width:80%%;" /></div>', img_path)
      return pandoc.RawBlock('html', html)
    else
      -- Return the original code block (no broken image)
      return el
    end
  end
end
