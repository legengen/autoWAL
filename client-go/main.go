package main

import (
	"embed"
	"log"

	"github.com/wailsapp/wails/v2"
	"github.com/wailsapp/wails/v2/pkg/options"
	"github.com/wailsapp/wails/v2/pkg/options/assetserver"
)

//go:embed all:frontend/dist
var assets embed.FS

func main() {
	app := NewApp()
	err := wails.Run(&options.App{
		Title:            "autoWAL 控制台",
		Width:            1180,
		Height:           760,
		MinWidth:         920,
		MinHeight:        620,
		BackgroundColour: &options.RGBA{R: 245, G: 247, B: 249, A: 1},
		AssetServer:      &assetserver.Options{Assets: assets},
		Bind:             []interface{}{app},
	})
	if err != nil {
		log.Fatal(err)
	}
}
