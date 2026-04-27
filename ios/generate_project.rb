#!/usr/bin/env ruby
# Generates the InverterMonitor.xcodeproj programmatically.
# Invoke via scripts/gen.sh which sets GEM_HOME.

require 'xcodeproj'
require 'pathname'
require 'fileutils'

ROOT = Pathname.new(File.expand_path('..', __FILE__))
PROJECT_DIR = ROOT + 'InverterMonitor'
PROJECT_PATH = PROJECT_DIR + 'InverterMonitor.xcodeproj'
SOURCE_ROOT = PROJECT_DIR + 'InverterMonitor'

# Start fresh so pbxproj stays deterministic.
FileUtils.rm_rf(PROJECT_PATH) if File.exist?(PROJECT_PATH)

project = Xcodeproj::Project.new(PROJECT_PATH.to_s, skip_initialization = false)
project.root_object.attributes['LastSwiftUpdateCheck'] = '1540'
project.root_object.attributes['LastUpgradeCheck'] = '1540'
project.root_object.attributes['ORGANIZATIONNAME'] = 'Bilal Ahmad'

# ---- Targets ------------------------------------------------------------
app_target = project.new_target(:application, 'InverterMonitor', :ios, '17.0')
app_target.build_configurations.each do |config|
  config.build_settings['PRODUCT_BUNDLE_IDENTIFIER'] = 'com.bilalahmad.InverterMonitor'
  config.build_settings['INFOPLIST_FILE'] = 'InverterMonitor/Resources/Info.plist'
  config.build_settings['TARGETED_DEVICE_FAMILY'] = '1,2' # iPhone + iPad
  config.build_settings['SWIFT_VERSION'] = '5.0'
  config.build_settings['IPHONEOS_DEPLOYMENT_TARGET'] = '17.0'
  config.build_settings['CODE_SIGN_STYLE'] = 'Automatic'
  # Signing is REQUIRED for device installs; we pass DEVELOPMENT_TEAM on the CLI when building.
  config.build_settings['CODE_SIGNING_REQUIRED'] = 'YES'
  config.build_settings['CODE_SIGNING_ALLOWED'] = 'YES'
  config.build_settings['DEVELOPMENT_TEAM'] = '6RWWV9NFH8'
  config.build_settings['CODE_SIGN_IDENTITY'] = 'Apple Development'
  config.build_settings['ENABLE_PREVIEWS'] = 'YES'
  config.build_settings['GENERATE_INFOPLIST_FILE'] = 'NO'
  config.build_settings['SUPPORTS_MACCATALYST'] = 'NO'
  config.build_settings['SUPPORTS_MAC_DESIGNED_FOR_IPHONE_IPAD'] = 'YES'
  config.build_settings['ASSETCATALOG_COMPILER_APPICON_NAME'] = 'AppIcon'
  config.build_settings['SWIFT_TREAT_WARNINGS_AS_ERRORS'] = 'YES'
  config.build_settings['GCC_TREAT_WARNINGS_AS_ERRORS'] = 'YES'
  config.build_settings['CLANG_WARN_DOCUMENTATION_COMMENTS'] = 'NO'
  config.build_settings['INFOPLIST_KEY_UILaunchScreen_Generation'] = 'YES'
  config.build_settings['INFOPLIST_KEY_UIApplicationSceneManifest_Generation'] = 'YES'
  config.build_settings['INFOPLIST_KEY_UISupportedInterfaceOrientations'] = 'UIInterfaceOrientationPortrait UIInterfaceOrientationLandscapeLeft UIInterfaceOrientationLandscapeRight'
  config.build_settings['INFOPLIST_KEY_UISupportedInterfaceOrientations_iPad'] = 'UIInterfaceOrientationPortrait UIInterfaceOrientationPortraitUpsideDown UIInterfaceOrientationLandscapeLeft UIInterfaceOrientationLandscapeRight'
end

# ---- Groups & file refs -------------------------------------------------
main_group = project.new_group('InverterMonitor', 'InverterMonitor')

def add_swift_files(project, target, group, dir, rel_base)
  abs = File.join(dir, rel_base)
  return unless File.directory?(abs)
  sub = group.new_group(rel_base, rel_base)
  Dir.entries(abs).sort.each do |entry|
    next if entry.start_with?('.')
    path = File.join(abs, entry)
    if File.directory?(path)
      add_swift_files(project, target, sub, abs, entry)
    elsif entry.end_with?('.swift')
      ref = sub.new_reference(entry)
      ref.last_known_file_type = 'sourcecode.swift'
      target.source_build_phase.add_file_reference(ref)
    end
  end
end

# Swift source folders
['App', 'Models', 'Services', 'ViewModels', 'Views'].each do |folder|
  add_swift_files(project, app_target, main_group, SOURCE_ROOT.to_s, folder)
end

# Resources: Assets.xcassets + Info.plist
res_group = main_group.new_group('Resources', 'Resources')

info_plist_path = 'InverterMonitor/Resources/Info.plist'
info_ref = res_group.new_reference('Info.plist')
info_ref.last_known_file_type = 'text.plist.xml'

res_group.path = 'Resources'

# Info.plist — relative to Resources group
info_ref.path = 'Info.plist'

# Assets.xcassets with our generated AppIcon.
assets_ref = res_group.new_reference('Assets.xcassets')
assets_ref.last_known_file_type = 'folder.assetcatalog'
assets_ref.path = 'Assets.xcassets'
app_target.resources_build_phase.add_file_reference(assets_ref)

# ---- Schemes -----------------------------------------------------------
project.save

# Build a shared scheme so `xcodebuild -scheme InverterMonitor` works.
scheme = Xcodeproj::XCScheme.new
scheme.add_build_target(app_target)
scheme.set_launch_target(app_target)
# save_as(..., shared: true) writes directly into xcshareddata/xcschemes.
scheme.save_as(PROJECT_PATH.to_s, 'InverterMonitor', true)

puts "Generated #{PROJECT_PATH}"
